"""API endpoints for Vector, Graph, and Hybrid RAG retrieval."""

from enum import StrEnum
from time import perf_counter

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.auth import Project
from app.datasets import owned
from app.dependencies import Db
from app.graph.service import source_location
from app.retrieval import (
    RetrievedChunk,
    graph_search,
    hybrid_search,
    reciprocal_rank_fusion,
    vector_search,
)

router = APIRouter(prefix="/v1/retrieval", tags=["retrieval"])


class RetrievalMode(StrEnum):
    VECTOR = "vector"
    GRAPH = "graph"
    HYBRID = "hybrid"


class RetrievalQueryRequest(BaseModel):
    query: str = Field(
        ..., min_length=1, max_length=1000, description="Query text to retrieve against"
    )
    dataset_id: str = Field(..., min_length=1, max_length=100, description="Dataset identifier")
    mode: RetrievalMode = Field(default=RetrievalMode.HYBRID, description="Retrieval mode")
    top_k: int = Field(default=10, ge=1, le=50, description="Maximum chunks to return")
    vector_weight: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Weight for vector rank in RRF"
    )
    graph_weight: float = Field(
        default=0.5, ge=0.0, le=1.0, description="Weight for graph rank in RRF"
    )
    compare: bool = Field(
        default=False,
        description=(
            "When true, executes vector, graph, and hybrid in parallel "
            "for side-by-side comparison"
        ),
    )


class ChunkEvidenceView(BaseModel):
    chunk_id: str
    document_id: str
    content: str
    score: float
    source: str
    vector_score: float | None = None
    graph_score: float | None = None
    entities: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    source_location: dict[str, int] | None = None


class ModeRetrievalResult(BaseModel):
    mode: str
    chunks: list[ChunkEvidenceView]
    latency_ms: float
    total_chunks: int
    entities_found: list[str] = Field(default_factory=list)
    relations_found: list[str] = Field(default_factory=list)


class RetrievalResponse(BaseModel):
    query: str
    dataset_id: str
    mode: str
    result: ModeRetrievalResult
    comparison: dict[str, ModeRetrievalResult] | None = None
    latency_ms: float


def _to_view(chunk: RetrievedChunk) -> ChunkEvidenceView:
    return ChunkEvidenceView(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        content=chunk.content,
        score=chunk.score,
        source=chunk.source,
        vector_score=chunk.vector_score,
        graph_score=chunk.graph_score,
        entities=chunk.entities,
        relations=chunk.relations,
        source_location=source_location(chunk.metadata),
    )


@router.post("/query", response_model=RetrievalResponse)
async def query_retrieval(
    body: RetrievalQueryRequest,
    project: Project,
    db: Db,
) -> RetrievalResponse:
    ds = await owned(db, project, body.dataset_id)
    dataset_id = ds.id
    total_start = perf_counter()

    if body.compare:
        # 1. Vector
        t_vec = perf_counter()
        vec_chunks = await vector_search(
            db, project.project_id, dataset_id, body.query, top_k=body.top_k
        )
        vec_latency = round((perf_counter() - t_vec) * 1000, 2)
        vec_result = ModeRetrievalResult(
            mode="vector",
            chunks=[_to_view(c) for c in vec_chunks],
            latency_ms=vec_latency,
            total_chunks=len(vec_chunks),
        )

        # 2. Graph
        t_graph = perf_counter()
        graph_chunks, entities, relations = await graph_search(
            db, project.project_id, dataset_id, body.query, top_k=body.top_k
        )
        graph_latency = round((perf_counter() - t_graph) * 1000, 2)
        graph_result = ModeRetrievalResult(
            mode="graph",
            chunks=[_to_view(c) for c in graph_chunks],
            latency_ms=graph_latency,
            total_chunks=len(graph_chunks),
            entities_found=entities,
            relations_found=relations,
        )

        # 3. Hybrid (Fuse using RRF)
        t_hybrid = perf_counter()
        fused_chunks = reciprocal_rank_fusion(
            vec_chunks,
            graph_chunks,
            top_k=body.top_k,
            vector_weight=body.vector_weight,
            graph_weight=body.graph_weight,
        )
        hybrid_latency = round((perf_counter() - t_hybrid) * 1000, 2)
        hybrid_result = ModeRetrievalResult(
            mode="hybrid",
            chunks=[_to_view(c) for c in fused_chunks],
            latency_ms=hybrid_latency,
            total_chunks=len(fused_chunks),
            entities_found=entities,
            relations_found=relations,
        )

        comparison = {
            "vector": vec_result,
            "graph": graph_result,
            "hybrid": hybrid_result,
        }
        selected = comparison.get(body.mode.value, hybrid_result)
        total_latency = round((perf_counter() - total_start) * 1000, 2)
        return RetrievalResponse(
            query=body.query,
            dataset_id=dataset_id,
            mode=body.mode.value,
            result=selected,
            comparison=comparison,
            latency_ms=total_latency,
        )

    # Single mode
    if body.mode == RetrievalMode.VECTOR:
        t0 = perf_counter()
        chunks = await vector_search(
            db, project.project_id, dataset_id, body.query, top_k=body.top_k
        )
        latency = round((perf_counter() - t0) * 1000, 2)
        mode_res = ModeRetrievalResult(
            mode="vector",
            chunks=[_to_view(c) for c in chunks],
            latency_ms=latency,
            total_chunks=len(chunks),
        )
    elif body.mode == RetrievalMode.GRAPH:
        t0 = perf_counter()
        chunks, entities, relations = await graph_search(
            db, project.project_id, dataset_id, body.query, top_k=body.top_k
        )
        latency = round((perf_counter() - t0) * 1000, 2)
        mode_res = ModeRetrievalResult(
            mode="graph",
            chunks=[_to_view(c) for c in chunks],
            latency_ms=latency,
            total_chunks=len(chunks),
            entities_found=entities,
            relations_found=relations,
        )
    else:
        t0 = perf_counter()
        chunks, entities, relations = await hybrid_search(
            db,
            project.project_id,
            dataset_id,
            body.query,
            top_k=body.top_k,
            vector_weight=body.vector_weight,
            graph_weight=body.graph_weight,
        )
        latency = round((perf_counter() - t0) * 1000, 2)
        mode_res = ModeRetrievalResult(
            mode="hybrid",
            chunks=[_to_view(c) for c in chunks],
            latency_ms=latency,
            total_chunks=len(chunks),
            entities_found=entities,
            relations_found=relations,
        )

    total_latency = round((perf_counter() - total_start) * 1000, 2)
    return RetrievalResponse(
        query=body.query,
        dataset_id=dataset_id,
        mode=body.mode.value,
        result=mode_res,
        comparison=None,
        latency_ms=total_latency,
    )
