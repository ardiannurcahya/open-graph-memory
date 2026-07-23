from threading import Lock
from time import sleep
from uuid import uuid4

import pytest
from app.config import Settings
from app.graph_dispatch import enqueue_graph_extraction
from app.graph_models import (
    CanonicalEntity,
    GraphEvidence,
    GraphExtractionRun,
    RelationAssertion,
    ReviewState,
    RunStatus,
)
from app.graph_pipeline import (
    ExtractorMetadata,
    _extract_chunks,
    _persist_chunk,
    build_extractor,
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


class SlowExtractor:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.lock = Lock()

    def extract(self, text: str) -> Extraction:
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        sleep(0.04)
        with self.lock:
            self.active -= 1
        return Extraction(entities=[Entity(name=text, type="Entity", confidence=1)], relations=[])


class FakeSession:
    def __init__(self) -> None:
        self.rows: dict[tuple[type[object], str], object] = {}
        self.commits = 0

    async def get(self, model: type[object], row_id: str) -> object | None:
        return self.rows.get((model, row_id))

    def add(self, row: object) -> None:
        row_id = getattr(row, "id", None) or getattr(row, "job_id", None)
        self.rows[(type(row), str(row_id))] = row

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        self.commits += 1


def inputs(dataset_id: str = "dataset-a") -> tuple[Document, Chunk]:
    project_id = uuid4()
    document = Document(id="doc", project_id=project_id, dataset_id=dataset_id)
    chunk = Chunk(
        id="chunk",
        project_id=project_id,
        dataset_id=dataset_id,
        document_id="doc",
        pipeline_version="test-v1",
        chunk_index=0,
        text="Acme [Org] employs Bob [Person]",
        token_count=7,
    )
    return document, chunk


def test_build_extractor_defaults_to_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.graph_pipeline.get_settings",
        lambda: Settings(graph_extractor_provider="deterministic"),
    )
    extractor, metadata = build_extractor()
    assert isinstance(extractor, DeterministicExtractor)
    assert metadata.provider == "deterministic"


def test_build_extractor_constructs_openai_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        graph_extractor_provider="openai",
        graph_extractor_model="test-model",
        graph_extractor_version="extractor-v2",
        graph_extractor_prompt_version="prompt-v3",
        openai_graph_extractor_base_url="https://extractor.example/v1",
        openai_api_key="test-secret",
    )
    monkeypatch.setattr("app.graph_pipeline.get_settings", lambda: settings)
    extractor, metadata = build_extractor()
    assert isinstance(extractor, OpenAICompatibleExtractor)
    assert extractor.timeout == settings.graph_extractor_timeout_seconds
    assert metadata.extractor_version == "extractor-v2"


@pytest.mark.asyncio
async def test_extract_chunks_respects_parallelism() -> None:
    project_id = uuid4()
    chunks = [
        Chunk(
            id=f"chunk-{index}",
            project_id=project_id,
            dataset_id="dataset-a",
            document_id="doc",
            pipeline_version="test-v1",
            chunk_index=index,
            text=f"Entity {index}",
            token_count=2,
        )
        for index in range(4)
    ]
    extractor = SlowExtractor()
    results = await _extract_chunks(chunks, extractor, parallelism=2)  # type: ignore[arg-type]
    assert [item.chunk.id for item in results] == [f"chunk-{index}" for index in range(4)]
    assert extractor.max_active == 2


@pytest.mark.asyncio
async def test_enqueue_persists_extractor_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        graph_extractor_provider="openai",
        graph_extractor_model="test-model",
        graph_extractor_version="extractor-v2",
        graph_extractor_prompt_version="prompt-v3",
        openai_api_key="test-secret",
    )
    monkeypatch.setattr("app.graph_pipeline.get_settings", lambda: settings)
    db = FakeSession()
    document, _ = inputs()
    job = await enqueue_graph_extraction(db, document)  # type: ignore[arg-type]
    assert (job.provider, job.model, job.extractor_version, job.prompt_version) == (
        "openai_compatible",
        "test-model",
        "extractor-v2",
        "prompt-v3",
    )


@pytest.mark.asyncio
async def test_duplicate_persistence_is_idempotent_with_provenance() -> None:
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
    evidence = [row for row in db.rows.values() if isinstance(row, GraphEvidence)]
    assert any(row.relation_id == relations[0].id and row.document_id == "doc" for row in evidence)


@pytest.mark.asyncio
async def test_temporal_rows_are_current_and_expired_entities_reactivate() -> None:
    db = FakeSession()
    document, chunk = inputs()
    extractor = Extractor(
        Extraction(entities=[Entity(name="Acme", type="Org", confidence=1)], relations=[])
    )
    metadata = ExtractorMetadata("deterministic", "model", "extractor-v1", "prompt-v1")
    await _persist_chunk(db, document, chunk, extractor, metadata)  # type: ignore[arg-type]
    entity = next(row for row in db.rows.values() if isinstance(row, CanonicalEntity))
    assert entity.valid_until is None
    first_valid_from = entity.valid_from
    entity.valid_until = first_valid_from
    run = next(row for row in db.rows.values() if isinstance(row, GraphExtractionRun))
    run.status = RunStatus.FAILED
    await _persist_chunk(db, document, chunk, extractor, metadata)  # type: ignore[arg-type]
    assert entity.valid_until is None
    assert entity.valid_from >= first_valid_from


@pytest.mark.asyncio
async def test_ambiguous_resolution_does_not_create_relation() -> None:
    db = FakeSession()
    document, chunk = inputs()
    chunk.text = "ACME [Org] and Acme [Product]"
    extractor = Extractor(
        Extraction(
            entities=[
                Entity(name="ACME", type="Org", confidence=1),
                Entity(name="Acme", type="Product", confidence=1),
            ],
            relations=[
                Relation(source="Acme", target="Acme", type="CONFUSED", confidence=1)
            ],
        )
    )
    await _persist_chunk(db, document, chunk, extractor)  # type: ignore[arg-type]
    assert not any(isinstance(row, RelationAssertion) for row in db.rows.values())


@pytest.mark.asyncio
async def test_provider_items_without_exact_evidence_are_skipped() -> None:
    db = FakeSession()
    document, chunk = inputs()
    extractor = Extractor(
        Extraction(
            entities=[
                Entity(name="Acme", type="Org", confidence=1),
                Entity(name="invented", type="Project", confidence=1),
            ],
            relations=[],
        )
    )
    await _persist_chunk(db, document, chunk, extractor)  # type: ignore[arg-type]
    names = {row.canonical_name for row in db.rows.values() if isinstance(row, CanonicalEntity)}
    assert names == {"Acme"}


@pytest.mark.asyncio
async def test_failed_provider_attempt_remains_running_for_caller_bookkeeping() -> None:
    db = FakeSession()
    document, chunk = inputs()
    with pytest.raises(RuntimeError, match="provider failed"):
        await _persist_chunk(db, document, chunk, Extractor(RuntimeError("provider failed")))  # type: ignore[arg-type]
    run = next(row for row in db.rows.values() if isinstance(row, GraphExtractionRun))
    assert run.status == RunStatus.RUNNING
    assert db.commits == 1


def test_temporal_models_expose_current_fact_fields() -> None:
    assert {"valid_from", "valid_until", "superseded_by"} <= set(
        CanonicalEntity.__table__.c.keys()
    )
    assert {"valid_from", "valid_until", "superseded_by"} <= set(
        RelationAssertion.__table__.c.keys()
    )
    assert ReviewState.UNREVIEWED.value == "unreviewed"
