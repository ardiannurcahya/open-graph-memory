"""Bounded, scoped graph retrieval and deterministic channel fusion."""

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol

from app.vector_store import VectorHit


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


def normalized_scores(hits: list[VectorHit]) -> dict[str, float]:
    if not hits:
        return {}
    values = [hit.score for hit in hits]
    low, high = min(values), max(values)
    if high == low:
        return {hit.id: 1.0 for hit in hits}
    return {hit.id: (hit.score - low) / (high - low) for hit in hits}


def fuse_hits(
    vector_hits: list[VectorHit],
    graph_hits: list[VectorHit],
    method: str,
    rrf_k: int,
    vector_weight: float,
    graph_weight: float,
) -> tuple[list[VectorHit], list[dict[str, object]]]:
    channels = {"vector": vector_hits, "graph": graph_hits}
    scores: dict[str, float] = {}
    sources: dict[str, VectorHit] = {}
    decisions: list[tuple[str, float, list[str]]] = []
    if method == "weighted":
        weights = {"vector": vector_weight, "graph": graph_weight}
        for channel, hits in channels.items():
            for hit in hits:
                sources.setdefault(hit.id, hit)
                scores[hit.id] = (
                    scores.get(hit.id, 0.0) + weights[channel] * normalized_scores(hits)[hit.id]
                )
    else:
        for _channel, hits in channels.items():
            for rank, hit in enumerate(hits, 1):
                sources.setdefault(hit.id, hit)
                scores[hit.id] = scores.get(hit.id, 0.0) + 1 / (rrf_k + rank)
    for chunk_id, score in scores.items():
        decisions.append(
            (
                chunk_id,
                score,
                [
                    name
                    for name, hits in channels.items()
                    if any(hit.id == chunk_id for hit in hits)
                ],
            )
        )
    decisions.sort(key=lambda item: (-item[1], item[0]))
    trace = [
        {"chunk_id": chunk_id, "score": score, "channels": names}
        for chunk_id, score, names in decisions
    ]
    return [
        VectorHit(chunk_id, score, sources[chunk_id].payload) for chunk_id, score, _ in decisions
    ], trace


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
    except Exception:
        return [], {
            "status": "fallback",
            "reason": "graph_unavailable",
            "latency_ms": round((perf_counter() - started) * 1000, 3),
        }
