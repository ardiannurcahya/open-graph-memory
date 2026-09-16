"""Unit and integration tests for Vector, Graph, and Hybrid RRF retrieval."""

from uuid import uuid4

import httpx
import pytest
from app.auth import ProjectContext, require_project
from app.dependencies import get_session
from app.graph.models import CanonicalEntity, GraphEvidence, ReviewState
from app.models import Chunk, Dataset, DatasetStatus, Document, DocumentStatus, Project
from app.retrieval import (
    RetrievedChunk,
    cosine_similarity,
    graph_search,
    hybrid_search,
    reciprocal_rank_fusion,
    vector_search,
)
from app.retrieval_api import router as retrieval_router
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession


def test_cosine_similarity_edge_cases() -> None:
    # Identical
    assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == 1.0
    # Scaled identical
    assert round(cosine_similarity([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]), 4) == 1.0
    # Orthogonal
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    # Opposite (clamped to 0.0)
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == 0.0
    # Empty or zero
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_reciprocal_rank_fusion_attribution_and_ranking() -> None:
    # Chunk A is top in vector, Chunk B is top in graph, Chunk C is in both
    vec_chunks = [
        RetrievedChunk(
            chunk_id="c_overlap",
            document_id="doc1",
            content="Overlap chunk",
            score=0.9,
            source="vector",
        ),
        RetrievedChunk(
            chunk_id="c_vec_only",
            document_id="doc1",
            content="Vector only",
            score=0.8,
            source="vector",
        ),
    ]
    graph_chunks = [
        RetrievedChunk(
            chunk_id="c_overlap",
            document_id="doc1",
            content="Overlap chunk",
            score=0.95,
            source="graph",
        ),
        RetrievedChunk(
            chunk_id="c_graph_only",
            document_id="doc1",
            content="Graph only",
            score=0.7,
            source="graph",
        ),
    ]

    fused = reciprocal_rank_fusion(
        vec_chunks, graph_chunks, top_k=5, k=60, vector_weight=0.5, graph_weight=0.5
    )

    assert len(fused) == 3
    # Overlap chunk should rank 1st because it appears in both rank lists
    assert fused[0].chunk_id == "c_overlap"
    assert fused[0].source == "hybrid"

    ids = [c.chunk_id for c in fused]
    assert "c_vec_only" in ids
    assert "c_graph_only" in ids

    # Check individual attribution
    for item in fused:
        if item.chunk_id == "c_vec_only":
            assert item.source == "vector"
        elif item.chunk_id == "c_graph_only":
            assert item.source == "graph"


def test_reciprocal_rank_fusion_empty_handling() -> None:
    assert reciprocal_rank_fusion([], []) == []
    single_vec = [
        RetrievedChunk(
            chunk_id="c1", document_id="doc1", content="Content", score=0.5, source="vector"
        )
    ]
    fused = reciprocal_rank_fusion(single_vec, [])
    assert len(fused) == 1
    assert fused[0].source == "vector"


@pytest.mark.asyncio
async def test_retrieval_hybrid_search_sqlite_flow(session: AsyncSession) -> None:
    project_id = uuid4()
    project = Project(id=project_id, name="Test Retrieval Project")
    session.add(project)

    dataset = Dataset(
        id="ds_test", project_id=project_id, name="Test DS", status=DatasetStatus.ACTIVE
    )
    session.add(dataset)

    doc = Document(
        id="doc_test",
        project_id=project_id,
        dataset_id="ds_test",
        filename="test.txt",
        mime_type="text/plain",
        size_bytes=100,
        content_hash="abc",
        object_key="docs/test.txt",
        status=DocumentStatus.INDEXED,
    )
    session.add(doc)

    # Embedding with 1536 dims
    emb1 = [0.1] * 1536
    emb2 = [0.0] * 1536
    emb2[0] = 1.0

    chunk1 = Chunk(
        id="chk_1",
        project_id=project_id,
        dataset_id="ds_test",
        document_id="doc_test",
        pipeline_version="v1",
        chunk_index=0,
        text="PostgreSQL pgvector enables dense semantic retrieval.",
        token_count=10,
        embedding=emb1,
    )
    chunk2 = Chunk(
        id="chk_2",
        project_id=project_id,
        dataset_id="ds_test",
        document_id="doc_test",
        pipeline_version="v1",
        chunk_index=1,
        text="Alice works closely with Bob at Acme Corporation.",
        token_count=10,
        embedding=emb2,
    )
    session.add_all([chunk1, chunk2])

    # Add canonical entity & evidence for graph search
    entity_alice = CanonicalEntity(
        id="ent_alice",
        project_id=project_id,
        dataset_id="ds_test",
        canonical_name="Alice",
        normalized_name="alice",
        entity_type="Person",
        confidence=0.95,
        review_state=ReviewState.APPROVED,
    )
    session.add(entity_alice)

    evidence = GraphEvidence(
        id="ev_1",
        project_id=project_id,
        dataset_id="ds_test",
        document_id="doc_test",
        chunk_id="chk_2",
        run_id="run_1",
        entity_id="ent_alice",
        relation_id=None,
        quote="Alice works closely with Bob",
        confidence=0.92,
    )
    session.add(evidence)
    await session.commit()

    # 1. Vector Search
    vec_results = await vector_search(session, project_id, "ds_test", "pgvector database", top_k=2)
    assert len(vec_results) == 2
    assert all(r.source == "vector" for r in vec_results)

    # 2. Graph Search
    graph_results, entities, relations = await graph_search(
        session, project_id, "ds_test", "Who is Alice?", top_k=2
    )
    assert len(graph_results) >= 1
    assert "Alice" in entities
    assert graph_results[0].chunk_id == "chk_2"
    assert graph_results[0].source == "graph"

    # 3. Hybrid Search
    hybrid_results, _, _ = await hybrid_search(
        session, project_id, "ds_test", "Alice works at Acme", top_k=5
    )
    assert len(hybrid_results) >= 1
    chk_ids = [r.chunk_id for r in hybrid_results]
    assert "chk_2" in chk_ids


@pytest.mark.asyncio
async def test_retrieval_api_endpoint(session: AsyncSession) -> None:
    project_id = uuid4()
    project = Project(id=project_id, name="Endpoint Test Project")
    session.add(project)

    dataset = Dataset(
        id="ds_retrieval_api",
        project_id=project_id,
        name="API Test DS",
        status=DatasetStatus.ACTIVE,
    )
    session.add(dataset)

    doc = Document(
        id="doc_api",
        project_id=project_id,
        dataset_id="ds_retrieval_api",
        filename="api.txt",
        mime_type="text/plain",
        size_bytes=50,
        content_hash="def",
        object_key="docs/api.txt",
        status=DocumentStatus.INDEXED,
    )
    session.add(doc)

    emb = [0.05] * 1536
    chunk = Chunk(
        id="chk_api",
        project_id=project_id,
        dataset_id="ds_retrieval_api",
        document_id="doc_api",
        pipeline_version="v1",
        chunk_index=0,
        text="Open Graph Memory provides unified graph and vector retrieval.",
        token_count=10,
        embedding=emb,
    )
    session.add(chunk)
    await session.commit()

    app = FastAPI()
    app.include_router(retrieval_router)

    async def get_project_override() -> ProjectContext:
        return ProjectContext(project_id)

    async def get_session_override() -> AsyncSession:
        return session

    app.dependency_overrides[require_project] = get_project_override
    app.dependency_overrides[get_session] = get_session_override

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Single mode: vector
        res = await client.post(
            "/v1/retrieval/query",
            json={
                "query": "vector retrieval",
                "dataset_id": "ds_retrieval_api",
                "mode": "vector",
                "top_k": 5,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "vector"
        assert len(data["result"]["chunks"]) == 1
        assert data["result"]["chunks"][0]["chunk_id"] == "chk_api"
        assert data["comparison"] is None

        # 2. Compare mode: true
        res_comp = await client.post(
            "/v1/retrieval/query",
            json={
                "query": "vector retrieval",
                "dataset_id": "ds_retrieval_api",
                "mode": "hybrid",
                "top_k": 5,
                "compare": True,
            },
        )
        assert res_comp.status_code == 200
        comp_data = res_comp.json()
        assert comp_data["comparison"] is not None
        assert "vector" in comp_data["comparison"]
        assert "graph" in comp_data["comparison"]
        assert "hybrid" in comp_data["comparison"]
        assert comp_data["comparison"]["vector"]["total_chunks"] == 1

        # 3. Not found dataset
        res_404 = await client.post(
            "/v1/retrieval/query",
            json={
                "query": "test",
                "dataset_id": "ds_non_existent",
            },
        )
        assert res_404.status_code == 404
