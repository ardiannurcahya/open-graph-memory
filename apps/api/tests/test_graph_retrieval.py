import pytest
from app.graph_store import Neo4jGraphStore


class RecordingGraph(Neo4jGraphStore):
    def __init__(self) -> None:
        super().__init__("http://neo4j", "user/password")
        self.statement = ""
        self.parameters: dict[str, object] = {}

    async def _records(
        self, statement: str, parameters: dict[str, object]
    ) -> list[dict[str, object]]:
        self.statement, self.parameters = statement, parameters
        return [
            {
                "chunk_id": "chunk-a",
                "relation_id": "rel-a",
                "seed_id": "entity-a",
                "neighbor_id": "entity-b",
                "confidence": 0.8,
            }
        ]


@pytest.mark.asyncio
async def test_traversal_scopes_every_graph_artifact_and_preserves_provenance() -> None:
    graph = RecordingGraph()
    evidence = await graph.traverse("project-a", "dataset-a", ["chunk-seed"], ["acme"], 2, 3, 2)
    assert evidence[0].path == ("entity-a", "rel-a", "entity-b")
    assert evidence[0].chunk_id == "chunk-a"
    assert graph.parameters["project_id"] == "project-a"
    assert graph.parameters["dataset_id"] == "dataset-a"
    assert "$dataset_id" in graph.statement and "$project_id" in graph.statement
    assert "LIMIT $limit" in graph.statement
    assert graph.parameters["limit"] == 6


@pytest.mark.asyncio
async def test_traversal_fanout_bounds_cycle_prone_results() -> None:
    graph = RecordingGraph()
    await graph.traverse("project-a", "dataset-a", [], [], 1, 4, 3)
    assert graph.parameters["limit"] == 12
    assert "ORDER BY r.id, e.chunk_id" in graph.statement
