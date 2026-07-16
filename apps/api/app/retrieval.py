"""Bounded, scoped graph retrieval."""

import asyncio
from dataclasses import dataclass
from time import perf_counter
from typing import Protocol


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
    except Exception:
        return [], {
            "status": "fallback",
            "reason": "graph_unavailable",
            "latency_ms": round((perf_counter() - started) * 1000, 3),
        }
