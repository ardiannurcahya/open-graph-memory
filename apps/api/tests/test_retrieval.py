import asyncio

import pytest
from app.retrieval import GraphEvidence, bounded_graph_search


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
