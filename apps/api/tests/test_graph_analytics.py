from typing import cast
from uuid import uuid4

import pytest
from app.graph_analytics import (
    LOUVAIN_RESOLUTION,
    LOUVAIN_SEED,
    analyze_graph,
    refresh_dataset_analytics,
)
from app.models import GraphAnalyticsRun
from sqlalchemy.ext.asyncio import AsyncSession


def test_analysis_is_deterministic_with_stable_community_ids() -> None:
    entities = ["a", "b", "c", "d"]
    relations = [("a", "b", 0.8), ("c", "d", 0.9)]

    first = analyze_graph(entities, relations)
    second = analyze_graph(list(reversed(entities)), list(reversed(relations)))

    assert first == second
    assert first.degree == {"a": 1, "b": 1, "c": 1, "d": 1}
    assert first.weighted_degree == {"a": 0.8, "b": 0.8, "c": 0.9, "d": 0.9}
    assert set(first.community_sizes.values()) == {2}
    assert LOUVAIN_SEED == 0
    assert LOUVAIN_RESOLUTION == 1.0


def test_analysis_retains_isolated_entities() -> None:
    result = analyze_graph(["connected", "isolated"], [])

    assert result.degree == {"connected": 0, "isolated": 0}
    assert len(result.communities) == 2
    assert sum(result.importance.values()) == 1.0


class AnalyticsSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.events: list[str] = []
        self.flushes: list[tuple[object, ...]] = []

    async def scalars(self, statement: object) -> list[str]:
        return ["entity"]

    async def execute(self, statement: object) -> list[tuple[str, str, float]]:
        return []

    async def scalar(self, statement: object) -> None:
        return None

    def add(self, row: object) -> None:
        self.added.append(row)
        self.events.append(type(row).__name__)

    async def flush(self) -> None:
        self.flushes.append(tuple(self.added))
        self.events.append("flush")


@pytest.mark.asyncio
async def test_refresh_flushes_run_before_adding_children() -> None:
    db = AnalyticsSession()

    await refresh_dataset_analytics(cast(AsyncSession, db), uuid4(), "dataset")

    assert len(db.flushes) == 2
    assert len(db.flushes[0]) == 1
    assert isinstance(db.flushes[0][0], GraphAnalyticsRun)
    assert len(db.flushes[1]) > len(db.flushes[0])
    assert db.events[:2] == ["GraphAnalyticsRun", "flush"]
    assert db.events[-1] == "flush"
