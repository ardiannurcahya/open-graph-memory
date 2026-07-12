from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
from app.config import Settings
from app.graph_dispatch import enqueue_graph_extraction
from app.graph_models import (
    CanonicalEntity,
    GraphEvidence,
    GraphExtractionRun,
    RelationAssertion,
    RunStatus,
)
from app.graph_pipeline import ExtractorMetadata, _persist_chunk, build_extractor
from app.graph_store import (
    ChunkProjection,
    DocumentProjection,
    EvidenceProjection,
    GraphProjection,
    Neo4jGraphStore,
    RelationProjection,
)
from app.models import Chunk, Document
from open_graph_core.extraction import (
    DeterministicExtractor,
    Entity,
    Extraction,
    OpenAICompatibleExtractor,
    Relation,
)


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
        row_id = getattr(row, "id", None)
        if row_id is None:
            row_id = getattr(row, "job_id", None)
        self.rows[(type(row), str(row_id))] = row

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


def test_timestamp_migration_covers_all_graph_artifacts() -> None:
    path = Path("apps/api/migrations/versions/0008_graph_artifact_timestamps.py")
    spec = spec_from_file_location("graph_artifact_timestamps", path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.down_revision == "0007"
    assert migration.TABLES == (
        "graph_extraction_runs",
        "canonical_entities",
        "entity_aliases",
        "relation_assertions",
        "graph_evidence",
        "entity_merge_history",
    )
    for model in (CanonicalEntity, RelationAssertion, GraphEvidence):
        assert {"created_at", "updated_at"} <= set(model.__table__.c.keys())


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


def test_build_extractor_defaults_to_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.graph_pipeline.get_settings", lambda: Settings())

    extractor, metadata = build_extractor()

    assert isinstance(extractor, DeterministicExtractor)
    assert metadata == ExtractorMetadata(
        provider="deterministic",
        model="deterministic-graph-v1",
        extractor_version="graph-extractor-v1",
        prompt_version="graph-v1",
    )


def test_build_extractor_constructs_openai_compatible_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        graph_extractor_provider="openai",
        graph_extractor_model="test-model",
        graph_extractor_version="test-extractor-v2",
        graph_extractor_prompt_version="test-prompt-v3",
        openai_base_url="https://extractor.example/v1",
        openai_api_key="test-secret",
    )
    monkeypatch.setattr("app.graph_pipeline.get_settings", lambda: settings)

    extractor, metadata = build_extractor()

    assert isinstance(extractor, OpenAICompatibleExtractor)
    assert (extractor.base_url, extractor.api_key, extractor.model, extractor.prompt_version) == (
        "https://extractor.example/v1",
        "test-secret",
        "test-model",
        "test-prompt-v3",
    )
    assert metadata.provider == "openai_compatible"
    assert metadata.extractor_version == "test-extractor-v2"


@pytest.mark.asyncio
async def test_enqueue_persists_selected_extractor_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        graph_extractor_provider="openai",
        graph_extractor_model="test-model",
        graph_extractor_version="test-extractor-v2",
        graph_extractor_prompt_version="test-prompt-v3",
        openai_api_key="test-secret",
    )
    monkeypatch.setattr("app.graph_pipeline.get_settings", lambda: settings)
    db = FakeSession()
    document, _ = inputs()

    job = await enqueue_graph_extraction(db, document)  # type: ignore[arg-type]

    assert (job.provider, job.model, job.extractor_version, job.prompt_version) == (
        "openai_compatible",
        "test-model",
        "test-extractor-v2",
        "test-prompt-v3",
    )


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
async def test_run_persists_selected_extractor_metadata() -> None:
    db = FakeSession()
    document, chunk = inputs()
    metadata = ExtractorMetadata(
        provider="openai_compatible",
        model="test-model",
        extractor_version="test-extractor-v2",
        prompt_version="test-prompt-v3",
    )

    await _persist_chunk(
        db,
        document,
        chunk,
        Extractor(Extraction(entities=[], relations=[])),  # type: ignore[arg-type]
        metadata,
    )

    run = next(row for row in db.rows.values() if isinstance(row, GraphExtractionRun))
    assert (run.provider, run.model, run.extractor_version, run.prompt_version) == (
        "openai_compatible",
        "test-model",
        "test-extractor-v2",
        "test-prompt-v3",
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
    timestamp = "2024-01-01T00:00:00+00:00"
    entity = GraphProjection(
        project_id, dataset_id, "entity", "Acme", "Org", 1, timestamp, timestamp
    )
    relation = RelationProjection(
        project_id, dataset_id, "relation", "entity", "entity-2", "EMPLOYS", "v1", 1,
        "unreviewed", timestamp, timestamp
    )
    chunk = ChunkProjection(project_id, dataset_id, document_id, "chunk", "pipeline-v1", timestamp)
    return DocumentProjection(
        project_id, dataset_id, document_id, timestamp, timestamp, (chunk,), (entity,), (relation,),
        (
            EvidenceProjection(
                project_id, dataset_id, "entity-evidence", document_id, "chunk", "entity", None,
                "run", "Acme", 1, "deterministic", "model", "v1", "prompt-v1", timestamp, timestamp
            ),
            EvidenceProjection(
                project_id, dataset_id, "relation-evidence", document_id, "chunk", None, "relation",
                "run", "Acme employs Bob", 1, "deterministic", "model", "v1", "prompt-v1",
                timestamp, timestamp
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
    assert "e.provider = row.provider" in statements
    assert "e.prompt_version = row.prompt_version" in statements
    assert "e.created_at = row.created_at" in statements
    assert "edge.evidence_id = row.evidence_id" in statements
    evidence_parameters = next(
        parameters
        for statement, parameters in store.calls
        if "e.provider = row.provider" in statement
    )
    assert evidence_parameters["rows"][0]["provider"] == "deterministic"
    assert evidence_parameters["rows"][0]["created_at"] == "2024-01-01T00:00:00+00:00"
    assert sum("DETACH DELETE e" in statement for statement, _ in store.calls) == 2
    assert sum("MERGE (p:Project" in statement for statement, _ in store.calls) == 2


@pytest.mark.asyncio
async def test_document_reconciliation_is_scoped_and_preserves_shared_graph_nodes() -> None:
    store = RecordingStore()
    await store.project_document(projection("project-a", "dataset-a", "doc-a"))
    stale_statement, stale_parameters = store.calls[0]
    assert "Evidence" in stale_statement and "document_id: $document_id" in stale_statement
    assert {key: stale_parameters[key] for key in ("project_id", "dataset_id", "document_id")} == {
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
