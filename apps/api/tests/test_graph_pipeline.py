from uuid import uuid4

import pytest
from app.graph_models import (
    CanonicalEntity,
    GraphEvidence,
    GraphExtractionRun,
    RelationAssertion,
    RunStatus,
)
from app.graph_pipeline import _persist_chunk
from app.graph_store import (
    DocumentProjection,
    EvidenceProjection,
    GraphProjection,
    Neo4jGraphStore,
    RelationProjection,
)
from app.models import Chunk, Document
from open_graph_core.extraction import Entity, Extraction, Relation


class Extractor:
    def __init__(self, result: Extraction | Exception) -> None:
        self.result = result
        self.calls = 0

    def extract(self, text: str) -> Extraction:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeSession:
    def __init__(self) -> None:
        self.rows: dict[tuple[type[object], str], object] = {}
        self.commits = 0

    async def get(self, model: type[object], row_id: str) -> object | None:
        return self.rows.get((model, row_id))

    def add(self, row: object) -> None:
        self.rows[(type(row), str(row.id))] = row

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1


class RecordingStore(Neo4jGraphStore):
    def __init__(self) -> None:
        super().__init__("http://neo4j", "user/password")
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def _run(self, statement: str, parameters: dict[str, object] | None = None) -> None:
        self.calls.append((statement, parameters or {}))


def inputs(dataset_id: str = "dataset-a") -> tuple[Document, Chunk]:
    project_id = uuid4()
    document = Document(id="doc", project_id=project_id, dataset_id=dataset_id)
    chunk = Chunk(
        id="chunk",
        project_id=project_id,
        dataset_id=dataset_id,
        document_id="doc",
        chunk_index=0,
        text="Acme [Org] employs Bob [Person]",
    )
    return document, chunk


@pytest.mark.asyncio
async def test_duplicate_execution_is_idempotent_and_persists_relation_provenance() -> None:
    db = FakeSession()
    document, chunk = inputs()
    extractor = Extractor(
        Extraction(
            entities=[
                Entity(name="Acme", type="Org", confidence=1),
                Entity(name="Bob", type="Person", confidence=0.8),
            ],
            relations=[Relation(source="Acme", target="Bob", type="EMPLOYS", confidence=0.6)],
        )
    )

    await _persist_chunk(db, document, chunk, extractor)  # type: ignore[arg-type]
    await _persist_chunk(db, document, chunk, extractor)  # type: ignore[arg-type]

    assert extractor.calls == 1
    relations = [row for row in db.rows.values() if isinstance(row, RelationAssertion)]
    assert len(relations) == 1
    relation = relations[0]
    entities = {
        row.canonical_name: row for row in db.rows.values() if isinstance(row, CanonicalEntity)
    }
    assert (
        relation.source_entity_id,
        relation.target_entity_id,
    ) == (entities["Acme"].id, entities["Bob"].id)
    evidence = next(
        row for row in db.rows.values() if isinstance(row, GraphEvidence) and row.relation_id
    )
    assert (
        evidence.document_id,
        evidence.chunk_id,
        evidence.run_id,
        evidence.confidence,
    ) == (
        "doc",
        "chunk",
        next(row.id for row in db.rows.values() if isinstance(row, GraphExtractionRun)),
        0.6,
    )


@pytest.mark.asyncio
async def test_resolution_is_exact_conservative_and_scoped() -> None:
    db = FakeSession()
    document, chunk = inputs("dataset-a")
    extractor = Extractor(
        Extraction(
            entities=[
                Entity(name="ACME", type="Org", confidence=1),
                Entity(name="Acme", type="Product", confidence=1),
            ],
            relations=[Relation(source="Acme", target="Acme", type="CONFUSED", confidence=1)],
        )
    )
    await _persist_chunk(db, document, chunk, extractor)  # type: ignore[arg-type]
    assert not any(isinstance(row, RelationAssertion) for row in db.rows.values())
    assert all(
        row.dataset_id == "dataset-a" and row.project_id == document.project_id
        for row in db.rows.values()
    )


@pytest.mark.asyncio
async def test_failed_attempt_is_durable_and_can_be_sanitized_by_caller() -> None:
    db = FakeSession()
    document, chunk = inputs()
    with pytest.raises(RuntimeError, match="secret-token"):
        await _persist_chunk(db, document, chunk, Extractor(RuntimeError("secret-token")))  # type: ignore[arg-type]
    run = next(row for row in db.rows.values() if isinstance(row, GraphExtractionRun))
    assert run.status == RunStatus.RUNNING
    assert db.commits == 1


def projection(
    project_id: str = "project", dataset_id: str = "dataset", document_id: str = "doc"
) -> DocumentProjection:
    entity = GraphProjection(project_id, dataset_id, "entity", "Acme", "Org", 1)
    relation = RelationProjection(
        project_id, dataset_id, "relation", "entity", "entity-2", "EMPLOYS", "v1", 1, "unreviewed"
    )
    return DocumentProjection(
        project_id,
        dataset_id,
        document_id,
        ("chunk",),
        (entity,),
        (relation,),
        (
            EvidenceProjection(
                project_id, dataset_id, "entity-evidence", document_id, "chunk", "entity", None
            ),
            EvidenceProjection(
                project_id, dataset_id, "relation-evidence", document_id, "chunk", None, "relation"
            ),
        ),
    )


@pytest.mark.asyncio
async def test_document_projection_creates_isolated_topology_and_is_idempotent() -> None:
    store = RecordingStore()
    await store.project_document(projection())
    await store.project_document(projection())

    statements = "\n".join(statement for statement, _ in store.calls)
    for edge in ("HAS_DATASET", "HAS_DOCUMENT", "HAS_CHUNK", "MENTIONS", "ASSERTS", "SUPPORTED_BY"):
        assert edge in statements
    assert "document_id: row.document_id" in statements
    assert sum("DETACH DELETE e" in statement for statement, _ in store.calls) == 2
    assert sum("MERGE (p:Project" in statement for statement, _ in store.calls) == 2


@pytest.mark.asyncio
async def test_document_reconciliation_is_scoped_and_preserves_shared_graph_nodes() -> None:
    store = RecordingStore()
    await store.project_document(projection("project-a", "dataset-a", "doc-a"))
    stale_statement, stale_parameters = store.calls[0]
    assert "Evidence" in stale_statement and "document_id: $document_id" in stale_statement
    assert stale_parameters == {
        "project_id": "project-a",
        "dataset_id": "dataset-a",
        "document_id": "doc-a",
    }
    assert all("DETACH DELETE n" not in statement for statement, _ in store.calls[:2])


@pytest.mark.asyncio
async def test_cypher_uses_parameters_for_user_controlled_ids() -> None:
    marker = "user-id-'} DETACH DELETE n //"
    store = RecordingStore()
    await store.project_document(projection(marker, marker, marker))
    await store.reconcile_dataset(marker, marker)
    for statement, parameters in store.calls:
        assert marker not in statement
        assert marker in repr(parameters)


@pytest.mark.asyncio
async def test_tenant_scoping_is_present_in_every_document_merge_and_match() -> None:
    store = RecordingStore()
    await store.project_document(projection("project-a", "dataset-a", "doc-a"))
    statements = "\n".join(statement for statement, _ in store.calls)
    assert "project_id: row.project_id, dataset_id: row.dataset_id" in statements
    assert "project_id: $project_id, dataset_id: $dataset_id, id: $document_id" in statements
    assert "MATCH (s:Entity {project_id: row.project_id, dataset_id: row.dataset_id" in statements
    assert "MATCH (c:Chunk {project_id: row.project_id, dataset_id: row.dataset_id" in statements
