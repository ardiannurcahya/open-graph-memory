import asyncio

import pytest
from app.retrieval import GraphEvidence, bounded_graph_search, fuse_hits
from app.vector_store import VectorHit


def hit(chunk_id: str, score: float) -> VectorHit:
    return VectorHit(chunk_id, score, {"document_id": "doc", "text": chunk_id})


def test_rrf_dedupes_and_orders_ties_stably() -> None:
    results, trace = fuse_hits(
        [hit("b", 0.9), hit("a", 0.8)], [hit("a", 0.7), hit("c", 0.6)], "rrf", 60, 0.5, 0.5
    )
    assert [item.id for item in results] == ["a", "b", "c"]
    assert trace[0]["channels"] == ["vector", "graph"]


def test_weighted_normalizes_channel_scores() -> None:
    results, _ = fuse_hits(
        [hit("a", 10), hit("b", 0)], [hit("b", 1), hit("c", 0)], "weighted", 60, 0.5, 0.5
    )
    assert [item.id for item in results] == ["a", "b", "c"]


class Outage:
    async def traverse(self, *args: object) -> list[GraphEvidence]:
        raise RuntimeError("down")


class Slow:
    async def traverse(self, *args: object) -> list[GraphEvidence]:
        await asyncio.sleep(1)
        return []


@pytest.mark.asyncio
async def test_graph_outage_and_timeout_have_safe_fallbacks() -> None:
    args = ("project", "dataset", [], [], 2, 2, 2)
    evidence, outage = await bounded_graph_search(Outage(), 10, *args)  # type: ignore[arg-type]
    assert evidence == [] and outage["reason"] == "graph_unavailable"
    evidence, timeout = await bounded_graph_search(Slow(), 1, *args)  # type: ignore[arg-type]
    assert evidence == [] and timeout["reason"] == "graph_timeout"
