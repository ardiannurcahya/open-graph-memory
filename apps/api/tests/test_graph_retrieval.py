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
        if "entity2" not in statement:
            return [
                {
                    "chunk_id": "chunk-a",
                    "evidence_chunk_ids": ["chunk-a"],
                    "path": ["entity-a", "rel-a", "entity-b"],
                    "entity_ids": ["entity-a", "entity-b"],
                    "relation_ids": ["rel-a"],
                    "confidence": 0.8,
                }
            ]
        return [
            {
                "chunk_id": "chunk-b",
                "evidence_chunk_ids": ["chunk-a", "chunk-b"],
                "path": ["entity-a", "rel-a", "entity-b", "rel-b", "entity-c"],
                "entity_ids": ["entity-a", "entity-b", "entity-c"],
                "relation_ids": ["rel-a", "rel-b"],
                "confidence": 0.8,
            }
        ]


class BootstrapRecordingGraph(Neo4jGraphStore):
    """Capture bootstrap DDL statements for index/constraint verification."""

    def __init__(self) -> None:
        super().__init__("http://neo4j", "user/password")
        self.statements: list[str] = []

    async def _run(self, statement: str, parameters: dict[str, object] | None = None) -> None:
        self.statements.append(statement)


@pytest.mark.asyncio
async def test_traversal_scopes_every_graph_artifact_and_preserves_provenance() -> None:
    graph = RecordingGraph()
    evidence = await graph.traverse("project-a", "dataset-a", ["chunk-seed"], ["acme"], 2, 3, 2)
    assert evidence[0].path == ("entity-a", "rel-a", "entity-b", "rel-b", "entity-c")
    assert evidence[0].relation_ids == ("rel-a", "rel-b")
    assert evidence[0].evidence_chunk_ids == ("chunk-a", "chunk-b")
    assert evidence[0].chunk_id == "chunk-b"
    assert graph.parameters["project_id"] == "project-a"
    assert graph.parameters["dataset_id"] == "dataset-a"
    assert "$dataset_id" in graph.statement and "$project_id" in graph.statement
    assert "SUPPORTED_BY" in graph.statement
    assert "toLower(seed.canonical_name)" in graph.statement
    assert "LIMIT $max_paths" in graph.statement
    assert graph.parameters["max_paths"] == 6
    assert "r1.id <> r2.id" in graph.statement


@pytest.mark.asyncio
async def test_traversal_fanout_bounds_cycle_prone_results() -> None:
    graph = RecordingGraph()
    await graph.traverse("project-a", "dataset-a", [], [], 1, 4, 3)
    assert graph.parameters["max_paths"] == 12
    assert "ORDER BY relation_ids, evidence_chunk_ids" in graph.statement


@pytest.mark.asyncio
async def test_depth_one_excludes_second_hop_and_depth_two_includes_it() -> None:
    graph = RecordingGraph()
    depth_one = await graph.traverse("project-a", "dataset-a", [], ["acme"], 1, 1, 1)
    assert depth_one[0].relation_ids == ("rel-a",)
    assert "entity2" not in graph.statement
    depth_two = await graph.traverse("project-a", "dataset-a", [], ["acme"], 2, 1, 1)
    assert depth_two[0].relation_ids == ("rel-a", "rel-b")
    assert "entity2" in graph.statement


@pytest.mark.asyncio
async def test_traversal_rejects_invalid_depth_and_caps_paths() -> None:
    graph = RecordingGraph()
    with pytest.raises(ValueError, match="depth"):
        await graph.traverse("project-a", "dataset-a", [], [], 3, 1, 1)
    await graph.traverse("project-a", "dataset-a", [], [], 2, 100, 100)
    assert graph.parameters["max_paths"] == 50


@pytest.mark.asyncio
async def test_traversal_fanout_caps_each_hop_via_call_subquery() -> None:
    """CALL subqueries with LIMIT $fanout prevent intermediate result explosion."""
    graph = RecordingGraph()
    await graph.traverse("project-a", "dataset-a", ["chunk-seed"], ["acme"], 2, 3, 2)
    assert graph.parameters["fanout"] == 3
    # First-hop fanout cap inside a CALL subquery
    assert "CALL { WITH seed" in graph.statement
    assert "ORDER BY r1.id LIMIT $fanout" in graph.statement
    # Second-hop fanout cap inside a CALL subquery
    assert "CALL { WITH seed, r1, entity1" in graph.statement
    assert "ORDER BY r2.id LIMIT $fanout" in graph.statement


@pytest.mark.asyncio
async def test_depth_one_also_caps_fanout() -> None:
    """One-hop query must also have the CALL subquery fanout cap."""
    graph = RecordingGraph()
    await graph.traverse("project-a", "dataset-a", [], ["acme"], 1, 5, 3)
    assert graph.parameters["fanout"] == 5
    assert "CALL { WITH seed" in graph.statement
    assert "ORDER BY r1.id LIMIT $fanout" in graph.statement
    assert "ORDER BY r2.id" not in graph.statement


@pytest.mark.asyncio
async def test_bootstrap_creates_traversal_indexes() -> None:
    """Bootstrap must create relationship property indexes for scoped traversal."""
    graph = BootstrapRecordingGraph()
    await graph.bootstrap()
    joined = "\n".join(graph.statements)
    # Node index for entity name lookup within project/dataset scope
    assert "CREATE INDEX entity_scope_name" in joined
    assert "e.canonical_name" in joined
    # Relationship property indexes for scoped traversals
    assert "CREATE INDEX source_scope" in joined
    assert "CREATE INDEX target_scope" in joined
    assert "CREATE INDEX supported_by_scope" in joined
    assert "CREATE INDEX mentions_scope" in joined
    # Original constraints still present
    assert "CREATE CONSTRAINT entity_scope_id" in joined
    assert "CREATE CONSTRAINT relation_scope_id" in joined
