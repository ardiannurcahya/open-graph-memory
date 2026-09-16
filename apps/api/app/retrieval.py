"""Bounded, scoped vector, graph, and hybrid retrieval engine with pgvector and RRF."""

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from time import perf_counter
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedding import EmbeddingProvider, get_embedding_provider
from app.graph.helpers import supported_entity
from app.graph.models import CanonicalEntity
from app.graph.models import GraphEvidence as DBGraphEvidence
from app.graph.service import bounded_walk, temporal_filter
from app.models import Chunk


@dataclass(frozen=True)
class GraphEvidence:
    chunk_id: str
    score: float
    path: tuple[str, ...]
    entity_ids: tuple[str, ...]
    relation_ids: tuple[str, ...]
    evidence_chunk_ids: tuple[str, ...]


class GraphRetriever(Protocol):
    async def traverse(
        self,
        project_id: str,
        dataset_id: str,
        seed_chunk_ids: list[str],
        seed_entity_names: list[str],
        max_depth: int,
        fanout: int,
        seed_limit: int,
    ) -> list[GraphEvidence]: ...


async def bounded_graph_search(
    graph: GraphRetriever,
    timeout_ms: int,
    project_id: str,
    dataset_id: str,
    seed_chunk_ids: list[str],
    seed_entity_names: list[str],
    max_depth: int,
    fanout: int,
    seed_limit: int,
) -> tuple[list[GraphEvidence], dict[str, object]]:
    started = perf_counter()
    try:
        if max_depth not in {1, 2}:
            raise ValueError("graph depth must be 1 or 2")
        evidence = await asyncio.wait_for(
            graph.traverse(
                project_id,
                dataset_id,
                seed_chunk_ids,
                seed_entity_names,
                max_depth,
                fanout,
                seed_limit,
            ),
            timeout_ms / 1000,
        )
        # Keep a stable best path per evidence chunk before it reaches query context.
        deduplicated = {
            item.chunk_id: item
            for item in sorted(evidence, key=lambda item: (-item.score, item.chunk_id, item.path))
        }
        return list(deduplicated.values()), {
            "status": "ok",
            "latency_ms": round((perf_counter() - started) * 1000, 3),
        }
    except TimeoutError:
        return [], {
            "status": "fallback",
            "reason": "graph_timeout",
            "latency_ms": round((perf_counter() - started) * 1000, 3),
        }
    except (ValueError, RuntimeError):
        return [], {
            "status": "fallback",
            "reason": "graph_unavailable",
            "latency_ms": round((perf_counter() - started) * 1000, 3),
        }


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    content: str
    score: float
    source: str  # "vector" | "graph" | "hybrid"
    vector_score: float | None = None
    graph_score: float | None = None
    entities: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(max(0.0, min(1.0, dot / (norm_a * norm_b))))


async def vector_search(
    db: AsyncSession,
    project_id: UUID,
    dataset_id: str,
    query: str,
    top_k: int = 10,
    embedding_provider: EmbeddingProvider | None = None,
) -> list[RetrievedChunk]:
    if not query.strip():
        return []
    provider = embedding_provider or get_embedding_provider()
    query_vector = await provider.embed_query(query)
    if not query_vector:
        return []

    is_postgres = db.bind is not None and db.bind.dialect.name == "postgresql"
    if is_postgres:
        try:
            stmt = (
                select(Chunk, Chunk.embedding.cosine_distance(query_vector).label("distance"))
                .where(
                    Chunk.project_id == project_id,
                    Chunk.dataset_id == dataset_id,
                    Chunk.embedding.is_not(None),
                )
                .order_by("distance")
                .limit(top_k)
            )
            rows = (await db.execute(stmt)).all()
            results: list[RetrievedChunk] = []
            for chunk, distance in rows:
                dist = float(distance) if distance is not None else 1.0
                score = round(max(0.0, min(1.0, 1.0 - dist)), 4)
                results.append(
                    RetrievedChunk(
                        chunk_id=chunk.id,
                        document_id=chunk.document_id,
                        content=chunk.text,
                        score=score,
                        source="vector",
                        vector_score=score,
                        metadata=chunk.metadata_ or {},
                    )
                )
            return results
        except Exception:
            pass

    # SQLite or in-memory fallback
    stmt = select(Chunk).where(
        Chunk.project_id == project_id,
        Chunk.dataset_id == dataset_id,
        Chunk.embedding.is_not(None),
    )
    chunks = list(await db.scalars(stmt))
    scored: list[tuple[float, Chunk]] = []
    for chunk in chunks:
        emb = chunk.embedding
        if emb is None:
            continue
        sim = cosine_similarity(query_vector, emb)
        scored.append((sim, chunk))

    scored.sort(key=lambda item: (-item[0], item[1].id))
    return [
        RetrievedChunk(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            content=chunk.text,
            score=round(sim, 4),
            source="vector",
            vector_score=round(sim, 4),
            metadata=chunk.metadata_ or {},
        )
        for sim, chunk in scored[:top_k]
    ]


async def graph_search(
    db: AsyncSession,
    project_id: UUID,
    dataset_id: str,
    query: str,
    top_k: int = 10,
) -> tuple[list[RetrievedChunk], list[str], list[str]]:
    if not query.strip():
        return [], [], []

    raw_tokens = [w.strip().lower() for w in re.split(r"[^\w\-_]+", query) if len(w.strip()) >= 2]
    filters = [
        CanonicalEntity.project_id == project_id,
        CanonicalEntity.dataset_id == dataset_id,
        supported_entity(),
        temporal_filter(entity=True),
    ]
    token_filters = [
        func.lower(CanonicalEntity.canonical_name).contains(tok, autoescape=True)
        for tok in raw_tokens[:10]
    ]
    if token_filters:
        filters.append(or_(*token_filters))

    seed_entities = list(
        await db.scalars(
            select(CanonicalEntity)
            .where(*filters)
            .order_by(CanonicalEntity.confidence.desc())
            .limit(5)
        )
    )

    if not seed_entities:
        all_dataset_entities = list(
            await db.scalars(
                select(CanonicalEntity)
                .where(
                    CanonicalEntity.project_id == project_id,
                    CanonicalEntity.dataset_id == dataset_id,
                    supported_entity(),
                    temporal_filter(entity=True),
                )
                .order_by(CanonicalEntity.confidence.desc())
                .limit(50)
            )
        )
        q_lower = query.lower()
        seed_entities = [e for e in all_dataset_entities if e.canonical_name.lower() in q_lower][:5]

    found_entity_ids: set[str] = set()
    found_relation_ids: set[str] = set()
    entity_names: list[str] = []
    relation_descriptions: list[str] = []

    for root in seed_entities:
        found_entity_ids.add(root.id)
        if root.canonical_name not in entity_names:
            entity_names.append(root.canonical_name)
        entities, relations, _ = await bounded_walk(
            db, project_id, dataset_id, root, depth=1, node_limit=10, relation_limit=15
        )
        for eid, ent in entities.items():
            found_entity_ids.add(eid)
            if ent.canonical_name not in entity_names:
                entity_names.append(ent.canonical_name)
        for rid, rel in relations.items():
            found_relation_ids.add(rid)
            src = entities.get(rel.source_entity_id)
            tgt = entities.get(rel.target_entity_id)
            src_name = src.canonical_name if src else rel.source_entity_id
            tgt_name = tgt.canonical_name if tgt else rel.target_entity_id
            desc = f"{src_name} -[{rel.relation_type}]-> {tgt_name}"
            if desc not in relation_descriptions:
                relation_descriptions.append(desc)

    if not found_entity_ids and not found_relation_ids:
        return [], entity_names, relation_descriptions

    evidence_filters = [
        DBGraphEvidence.project_id == project_id,
        DBGraphEvidence.dataset_id == dataset_id,
    ]
    subject_filters = []
    if found_entity_ids:
        subject_filters.append(DBGraphEvidence.entity_id.in_(found_entity_ids))
    if found_relation_ids:
        subject_filters.append(DBGraphEvidence.relation_id.in_(found_relation_ids))
    evidence_filters.append(or_(*subject_filters))

    evidence_rows = list(
        await db.execute(
            select(DBGraphEvidence, Chunk)
            .join(Chunk, Chunk.id == DBGraphEvidence.chunk_id)
            .where(*evidence_filters)
            .order_by(DBGraphEvidence.confidence.desc())
            .limit(top_k * 3)
        )
    )

    chunk_map: dict[str, RetrievedChunk] = {}
    for ev, chk in evidence_rows:
        conf = float(ev.confidence)
        if chk.id not in chunk_map:
            chunk_map[chk.id] = RetrievedChunk(
                chunk_id=chk.id,
                document_id=chk.document_id,
                content=chk.text,
                score=round(conf, 4),
                source="graph",
                graph_score=round(conf, 4),
                entities=[e for e in entity_names if e.lower() in chk.text.lower()],
                relations=[
                    r
                    for r in relation_descriptions
                    if any(part in chk.text for part in r.split(" -["))
                ],
                metadata=chk.metadata_ or {},
            )
        else:
            curr = chunk_map[chk.id]
            curr.score = round(max(curr.score, conf), 4)
            curr.graph_score = curr.score

    sorted_chunks = sorted(chunk_map.values(), key=lambda c: (-c.score, c.chunk_id))[:top_k]
    return sorted_chunks, entity_names[:10], relation_descriptions[:10]


def reciprocal_rank_fusion(
    vector_results: list[RetrievedChunk],
    graph_results: list[RetrievedChunk],
    top_k: int = 10,
    k: int = 60,
    vector_weight: float = 0.5,
    graph_weight: float = 0.5,
) -> list[RetrievedChunk]:
    if not vector_results and not graph_results:
        return []

    chunk_store: dict[str, RetrievedChunk] = {}
    vec_ranks: dict[str, int] = {}
    graph_ranks: dict[str, int] = {}

    for rank, chunk in enumerate(vector_results, start=1):
        vec_ranks[chunk.chunk_id] = rank
        chunk_store[chunk.chunk_id] = chunk

    for rank, chunk in enumerate(graph_results, start=1):
        graph_ranks[chunk.chunk_id] = rank
        if chunk.chunk_id not in chunk_store:
            chunk_store[chunk.chunk_id] = chunk
        else:
            existing = chunk_store[chunk.chunk_id]
            existing.graph_score = chunk.graph_score
            merged_entities = list(dict.fromkeys(existing.entities + chunk.entities))
            merged_relations = list(dict.fromkeys(existing.relations + chunk.relations))
            existing.entities = merged_entities
            existing.relations = merged_relations

    all_ids = set(vec_ranks.keys()) | set(graph_ranks.keys())
    rrf_scores: dict[str, float] = {}
    for cid in all_ids:
        v_rank = vec_ranks.get(cid)
        g_rank = graph_ranks.get(cid)
        v_comp = (vector_weight / (k + v_rank)) if v_rank is not None else 0.0
        g_comp = (graph_weight / (k + g_rank)) if g_rank is not None else 0.0
        rrf_scores[cid] = v_comp + g_comp

    max_possible = (
        (vector_weight + graph_weight) / (k + 1) if (vector_weight + graph_weight) > 0 else 1.0
    )

    sorted_ids = sorted(all_ids, key=lambda cid: (-rrf_scores[cid], cid))[:top_k]
    fused: list[RetrievedChunk] = []
    for cid in sorted_ids:
        base = chunk_store[cid]
        in_vec = cid in vec_ranks
        in_graph = cid in graph_ranks
        source = "hybrid" if (in_vec and in_graph) else ("vector" if in_vec else "graph")
        normalized_score = round(min(1.0, rrf_scores[cid] / max_possible), 4)

        fused.append(
            RetrievedChunk(
                chunk_id=base.chunk_id,
                document_id=base.document_id,
                content=base.content,
                score=normalized_score,
                source=source,
                vector_score=base.vector_score,
                graph_score=base.graph_score,
                entities=base.entities,
                relations=base.relations,
                metadata=base.metadata,
            )
        )
    return fused


async def hybrid_search(
    db: AsyncSession,
    project_id: UUID,
    dataset_id: str,
    query: str,
    top_k: int = 10,
    vector_weight: float = 0.5,
    graph_weight: float = 0.5,
    k: int = 60,
    embedding_provider: EmbeddingProvider | None = None,
) -> tuple[list[RetrievedChunk], list[str], list[str]]:
    vector_results = await vector_search(
        db, project_id, dataset_id, query, top_k=top_k * 2, embedding_provider=embedding_provider
    )
    graph_results, entities, relations = await graph_search(
        db, project_id, dataset_id, query, top_k=top_k * 2
    )
    fused = reciprocal_rank_fusion(
        vector_results,
        graph_results,
        top_k=top_k,
        k=k,
        vector_weight=vector_weight,
        graph_weight=graph_weight,
    )
    return fused, entities, relations
