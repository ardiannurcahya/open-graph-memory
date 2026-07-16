"""Authoritative extraction persistence followed by rebuildable Neo4j projection."""

import hashlib
import logging
from asyncio import Semaphore, gather, to_thread
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from open_graph_contracts import PluginConfig, SecretValue
from open_graph_core.extraction import (
    Extraction,
    Extractor,
    normalize_name,
    stable_id,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db import engine
from app.graph_analytics import refresh_dataset_analytics
from app.graph_models import (
    CanonicalEntity,
    GraphEvidence,
    GraphExtractionRun,
    RelationAssertion,
    ReviewState,
    RunStatus,
)
from app.graph_store import (
    ChunkProjection,
    DocumentProjection,
    EvidenceProjection,
    GraphProjection,
    GraphStore,
    RelationProjection,
)
from app.ingestion import sanitized_error
from app.models import Chunk, Document, DocumentStatus
from app.plugin_registry import create_extractor, create_graph_store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractorMetadata:
    provider: str
    model: str
    extractor_version: str
    prompt_version: str


@dataclass(frozen=True)
class ChunkExtractionResult:
    chunk: Chunk
    extraction: Extraction


def extractor_metadata() -> ExtractorMetadata:
    settings = get_settings()
    return ExtractorMetadata(
        provider={
            "openai": "openai_compatible",
            "nlp": "nlp",
            "deterministic": "deterministic",
        }[settings.graph_extractor_provider],
        model=settings.graph_extractor_model,
        extractor_version=settings.graph_extractor_version,
        prompt_version=settings.graph_extractor_prompt_version,
    )


def build_extractor() -> tuple[Extractor, ExtractorMetadata]:
    settings = get_settings()
    metadata = extractor_metadata()
    return (
        create_extractor(
            settings.graph_extractor_provider,
            PluginConfig(
                {
                    "base_url": settings.graph_extractor_base_url,
                    "model": settings.graph_extractor_model,
                    "prompt_version": settings.graph_extractor_prompt_version,
                    "timeout": settings.graph_extractor_timeout_seconds,
                },
                {"api_key": SecretValue(settings.openai_api_key.get_secret_value())},
            ),
        ),
        metadata,
    )


def _store() -> GraphStore:
    settings = get_settings()
    return create_graph_store(
        PluginConfig(
            {"url": settings.neo4j_url},
            {"auth": SecretValue(settings.neo4j_auth.get_secret_value())},
        )
    )


async def extract_document(
    document_id: str,
    extractor: Extractor | None = None,
    graph: GraphStore | None = None,
    on_batch_committed: Callable[[], Awaitable[None]] | None = None,
) -> str:
    selected_extractor, metadata = (
        build_extractor()
        if extractor is None
        else (
            extractor,
            extractor_metadata(),
        )
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        document = await db.get(Document, document_id)
        if document is None or document.status not in {
            DocumentStatus.INDEXED,
            DocumentStatus.PERSISTING,
        }:
            raise ValueError("graph extraction requires a persisted document")
        chunks = list(
            await db.scalars(
                select(Chunk)
                .where(
                    Chunk.project_id == document.project_id,
                    Chunk.dataset_id == document.dataset_id,
                    Chunk.document_id == document.id,
                )
                .order_by(Chunk.chunk_index)
            )
        )
        try:
            pending_chunks = [
                chunk
                for chunk in chunks
                if not await _chunk_run_succeeded(db, chunk, metadata)
            ]
            parallelism = get_settings().graph_extractor_parallelism
            logger.info(
                "graph extraction started document=%s chunks=%d pending=%d parallelism=%d",
                document.id,
                len(chunks),
                len(pending_chunks),
                parallelism,
            )
            completed = 0
            active_batch: list[Chunk] = []
            for active_batch in _batches(pending_chunks, parallelism):
                for chunk in active_batch:
                    await _ensure_running_run(db, document, chunk, metadata)
                await db.commit()
                extracted, extraction_error = await _extract_batch(
                    active_batch, selected_extractor, parallelism
                )
                for item in extracted:
                    await _persist_chunk_result(db, document, item.chunk, item.extraction, metadata)
                    completed += 1
                    logger.info(
                        "graph extraction chunk persisted document=%s progress=%d/%d",
                        document.id,
                        completed,
                        len(pending_chunks),
                    )
                await db.commit()
                if on_batch_committed is not None:
                    await on_batch_committed()
                if extraction_error is not None:
                    raise extraction_error
            await project_document(db, document, graph or _store())
            logger.info("graph projection completed document=%s", document.id)
            await refresh_dataset_analytics(db, document.project_id, document.dataset_id)
            await db.commit()
            logger.info("graph analytics refreshed dataset=%s", document.dataset_id)
            return document.id
        except BaseException as exc:
            await db.rollback()
            for chunk in active_batch:
                chunk_id, chunk_text = chunk.id, chunk.text
                run_id = stable_id("run", chunk_id, metadata.extractor_version, _hash(chunk_text))
                run = await db.get(GraphExtractionRun, run_id)
                if run is not None and run.status != RunStatus.SUCCEEDED:
                    run.status = RunStatus.FAILED
                    run.error_message = sanitized_error(exc)
                    run.completed_at = datetime.now(UTC)
            await db.commit()
            logger.exception("graph extraction failed for document %s", document_id)
            raise


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _batches(chunks: list[Chunk], size: int) -> Iterator[list[Chunk]]:
    for start in range(0, len(chunks), size):
        yield chunks[start : start + size]


async def _chunk_run_succeeded(
    db: AsyncSession, chunk: Chunk, metadata: ExtractorMetadata
) -> bool:
    run_id = stable_id("run", chunk.id, metadata.extractor_version, _hash(chunk.text))
    run = await db.get(GraphExtractionRun, run_id)
    return run is not None and run.status == RunStatus.SUCCEEDED


async def _ensure_running_run(
    db: AsyncSession, document: Document, chunk: Chunk, metadata: ExtractorMetadata
) -> GraphExtractionRun:
    input_hash = _hash(chunk.text)
    run_id = stable_id("run", chunk.id, metadata.extractor_version, input_hash)
    run = await db.get(GraphExtractionRun, run_id)
    if run is None:
        run = GraphExtractionRun(
            id=run_id,
            project_id=document.project_id,
            dataset_id=document.dataset_id,
            document_id=document.id,
            chunk_id=chunk.id,
            status=RunStatus.RUNNING,
            provider=metadata.provider,
            model=metadata.model,
            extractor_version=metadata.extractor_version,
            prompt_version=metadata.prompt_version,
            ontology_version=None,
            input_hash=input_hash,
        )
        db.add(run)
        await db.flush()
    else:
        run.status = RunStatus.RUNNING
        run.error_message = None
        run.completed_at = None
    return run


async def _extract_chunks(
    chunks: list[Chunk], extractor: Extractor, parallelism: int
) -> list[ChunkExtractionResult]:
    results, error = await _extract_batch(chunks, extractor, parallelism)
    if error is not None:
        raise error
    return results


async def _extract_batch(
    chunks: list[Chunk], extractor: Extractor, parallelism: int
) -> tuple[list[ChunkExtractionResult], BaseException | None]:
    if parallelism <= 1:
        results: list[ChunkExtractionResult] = []
        for chunk in chunks:
            try:
                results.append(ChunkExtractionResult(chunk, extractor.extract(chunk.text)))
            except BaseException as exc:
                return results, exc
        return results, None
    semaphore = Semaphore(parallelism)

    async def run(chunk: Chunk) -> ChunkExtractionResult:
        async with semaphore:
            return ChunkExtractionResult(chunk, await to_thread(extractor.extract, chunk.text))

    outcomes = await gather(*(run(chunk) for chunk in chunks), return_exceptions=True)
    results = [outcome for outcome in outcomes if isinstance(outcome, ChunkExtractionResult)]
    error = next((outcome for outcome in outcomes if isinstance(outcome, BaseException)), None)
    return results, error


async def _persist_chunk(
    db: AsyncSession,
    document: Document,
    chunk: Chunk,
    extractor: Extractor,
    metadata: ExtractorMetadata | None = None,
) -> None:
    metadata = metadata or extractor_metadata()
    if await _chunk_run_succeeded(db, chunk, metadata):
        return
    run = await _ensure_running_run(db, document, chunk, metadata)
    # Keep the attempt record if provider extraction fails.
    await db.commit()
    result = extractor.extract(chunk.text)
    await _persist_chunk_result(db, document, chunk, result, metadata, run)


async def _persist_chunk_result(
    db: AsyncSession,
    document: Document,
    chunk: Chunk,
    result: Extraction,
    metadata: ExtractorMetadata,
    run: GraphExtractionRun | None = None,
) -> None:
    input_hash = _hash(chunk.text)
    run_id = stable_id("run", chunk.id, metadata.extractor_version, input_hash)
    if run is None:
        run = await db.get(GraphExtractionRun, run_id)
    if run is not None and run.status == RunStatus.SUCCEEDED:
        return
    if run is None:
        run = await _ensure_running_run(db, document, chunk, metadata)
    else:
        run.status = RunStatus.RUNNING
        run.error_message = None
        run.completed_at = None
    entities: dict[str, list[CanonicalEntity]] = {}
    for entity_item in result.entities:
        normalized = normalize_name(entity_item.name)
        entity_id = stable_id(
            "ent",
            str(document.project_id),
            document.dataset_id,
            normalized,
            normalize_name(entity_item.type),
        )
        entity = await db.get(CanonicalEntity, entity_id)
        if entity is None:
            entity = CanonicalEntity(
                id=entity_id,
                project_id=document.project_id,
                dataset_id=document.dataset_id,
                canonical_name=entity_item.name,
                normalized_name=normalized,
                entity_type=entity_item.type,
                confidence=entity_item.confidence,
                version=1,
                review_state=ReviewState.UNREVIEWED
                if entity_item.confidence == 1
                else ReviewState.NEEDS_REVIEW,
            )
            db.add(entity)
        entities.setdefault(normalized, []).append(entity)
        evidence_id = stable_id("ev", run_id, entity_id)
        if await db.get(GraphEvidence, evidence_id) is None:
            offset = chunk.text.find(entity_item.name)
            db.add(
                GraphEvidence(
                    id=evidence_id,
                    project_id=document.project_id,
                    dataset_id=document.dataset_id,
                    document_id=document.id,
                    chunk_id=chunk.id,
                    run_id=run_id,
                    entity_id=entity_id,
                    relation_id=None,
                    quote=entity_item.name,
                    start_offset=offset if offset >= 0 else None,
                    end_offset=offset + len(entity_item.name) if offset >= 0 else None,
                    confidence=entity_item.confidence,
                )
            )
    await db.flush()
    for relation_item in result.relations:
        source_matches = entities.get(normalize_name(relation_item.source), [])
        target_matches = entities.get(normalize_name(relation_item.target), [])
        source = source_matches[0] if len(source_matches) == 1 else None
        target = target_matches[0] if len(target_matches) == 1 else None
        if source is None or target is None or source.id == target.id:
            continue
        relation_id = stable_id(
            "rel",
            document.dataset_id,
            source.id,
            relation_item.type,
            target.id,
            metadata.extractor_version,
        )
        relation = await db.get(RelationAssertion, relation_id)
        if relation is None:
            relation = RelationAssertion(
                id=relation_id,
                project_id=document.project_id,
                dataset_id=document.dataset_id,
                source_entity_id=source.id,
                target_entity_id=target.id,
                relation_type=relation_item.type,
                confidence=relation_item.confidence,
                extractor_version=metadata.extractor_version,
                review_state=ReviewState.UNREVIEWED
                if relation_item.confidence == 1
                else ReviewState.NEEDS_REVIEW,
            )
            db.add(relation)
        evidence_id = stable_id("ev", run_id, relation_id)
        if await db.get(GraphEvidence, evidence_id) is None:
            db.add(
                GraphEvidence(
                    id=evidence_id,
                    project_id=document.project_id,
                    dataset_id=document.dataset_id,
                    document_id=document.id,
                    chunk_id=chunk.id,
                    run_id=run_id,
                    entity_id=None,
                    relation_id=relation_id,
                    quote=chunk.text,
                    start_offset=0,
                    end_offset=len(chunk.text),
                    confidence=relation_item.confidence,
                )
            )
    run.status, run.error_message, run.completed_at = RunStatus.SUCCEEDED, None, datetime.now(UTC)


async def project_document(db: AsyncSession, document: Document, graph: GraphStore) -> None:
    chunks = list(
        await db.scalars(
            select(Chunk).where(
                Chunk.project_id == document.project_id,
                Chunk.dataset_id == document.dataset_id,
                Chunk.document_id == document.id,
            )
        )
    )
    entities = list(
        await db.scalars(
            select(CanonicalEntity).where(
                CanonicalEntity.project_id == document.project_id,
                CanonicalEntity.dataset_id == document.dataset_id,
            )
        )
    )
    relations = list(
        await db.scalars(
            select(RelationAssertion).where(
                RelationAssertion.project_id == document.project_id,
                RelationAssertion.dataset_id == document.dataset_id,
            )
        )
    )
    evidence = list(
        await db.scalars(
            select(GraphEvidence).where(
                GraphEvidence.project_id == document.project_id,
                GraphEvidence.dataset_id == document.dataset_id,
                GraphEvidence.document_id == document.id,
            )
        )
    )
    runs = {
        run.id: run
        for run in await db.scalars(
            select(GraphExtractionRun).where(
                GraphExtractionRun.project_id == document.project_id,
                GraphExtractionRun.dataset_id == document.dataset_id,
                GraphExtractionRun.document_id == document.id,
            )
        )
    }
    await graph.bootstrap()
    await graph.project_document(
        DocumentProjection(
            project_id=str(document.project_id),
            dataset_id=document.dataset_id,
            document_id=document.id,
            document_created_at=document.created_at.isoformat(),
            document_updated_at=document.updated_at.isoformat(),
            chunks=tuple(
                ChunkProjection(
                    str(chunk.project_id),
                    chunk.dataset_id,
                    chunk.document_id,
                    chunk.id,
                    chunk.pipeline_version,
                    chunk.created_at.isoformat(),
                )
                for chunk in chunks
            ),
            entities=tuple(
                GraphProjection(
                    str(e.project_id),
                    e.dataset_id,
                    e.id,
                    e.canonical_name,
                    e.entity_type,
                    e.version,
                    e.created_at.isoformat(),
                    e.updated_at.isoformat(),
                )
                for e in entities
            ),
            relations=tuple(
                RelationProjection(
                    str(r.project_id),
                    r.dataset_id,
                    r.id,
                    r.source_entity_id,
                    r.target_entity_id,
                    r.relation_type,
                    r.extractor_version,
                    r.confidence,
                    r.review_state.value,
                    r.created_at.isoformat(),
                    r.updated_at.isoformat(),
                )
                for r in relations
            ),
            evidence=tuple(
                EvidenceProjection(
                    str(item.project_id),
                    item.dataset_id,
                    item.id,
                    item.document_id,
                    item.chunk_id,
                    item.entity_id,
                    item.relation_id,
                    item.run_id,
                    item.quote,
                    item.confidence,
                    runs[item.run_id].provider,
                    runs[item.run_id].model,
                    runs[item.run_id].extractor_version,
                    runs[item.run_id].prompt_version,
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                )
                for item in evidence
            ),
        )
    )


async def rebuild_dataset(project_id: str, dataset_id: str, graph: GraphStore | None = None) -> int:
    target = graph or _store()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        documents = list(
            await db.scalars(
                select(Document).where(
                    Document.project_id == project_id,
                    Document.dataset_id == dataset_id,
                    Document.status == DocumentStatus.INDEXED,
                )
            )
        )
        await target.reconcile_dataset(project_id, dataset_id)
        for document in documents:
            await project_document(db, document, target)
        return len(documents)
