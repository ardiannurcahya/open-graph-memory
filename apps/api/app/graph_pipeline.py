"""Authoritative extraction persistence with temporal tracking."""

import hashlib
import json
import logging
from asyncio import Semaphore, gather, to_thread
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from open_graph_contracts import PluginConfig, SecretValue
from open_graph_core.extraction import (
    ChunkExtractionContext,
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
from app.graph_consolidation import (
    ConsolidationOutput,
    build_input,
    consolidate_openai,
    validate_output,
)
from app.graph_models import (
    CanonicalEntity,
    EntityAlias,
    EntityAliasEvidence,
    GraphConsolidationRun,
    GraphEvidence,
    GraphExtractionRun,
    RelationAssertion,
    ReviewState,
    RunStatus,
)
from app.ingestion import sanitized_error
from app.models import Chunk, Document, DocumentStatus
from app.plugin_registry import create_extractor

logger = logging.getLogger(__name__)


class _ContextualExtractor(Protocol):
    def extract_with_context(self, context: ChunkExtractionContext) -> Extraction: ...


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


def _chunk_contexts(
    document: Document, chunks: list[Chunk], excerpt_chars: int
) -> dict[str, ChunkExtractionContext]:
    contexts: dict[str, ChunkExtractionContext] = {}
    for index, chunk in enumerate(chunks):
        metadata = chunk.metadata_ or {}
        raw_path = metadata.get("section_path", [])
        section_path = tuple(str(item) for item in raw_path) if isinstance(raw_path, list) else ()
        page = metadata.get("page_number")
        contexts[chunk.id] = ChunkExtractionContext(
            document_title=document.filename or document.id,
            section_path=section_path,
            page_number=page if isinstance(page, int) else None,
            chunk_index=chunk.chunk_index,
            chunk_count=len(chunks),
            previous_excerpt=chunks[index - 1].text[-excerpt_chars:] if index else "",
            target_text=chunk.text,
            next_excerpt=chunks[index + 1].text[:excerpt_chars] if index + 1 < len(chunks) else "",
        )
    return contexts


def _extract_one(extractor: Extractor, context: ChunkExtractionContext) -> Extraction:
    contextual = getattr(extractor, "extract_with_context", None)
    if callable(contextual):
        return cast(_ContextualExtractor, extractor).extract_with_context(context)
    return extractor.extract(context.target_text)


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



async def extract_document(
    document_id: str,
    extractor: Extractor | None = None,
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
            settings = get_settings()
            pending_chunks = [
                chunk for chunk in chunks if not await _chunk_run_succeeded(db, chunk, metadata)
            ]
            parallelism = settings.graph_extractor_parallelism
            contexts = _chunk_contexts(
                document, chunks, settings.graph_document_context_excerpt_chars
            )
            logger.info(
                "graph extraction started document=%s chunks=%d pending=%d parallelism=%d",
                document.id,
                len(chunks),
                len(pending_chunks),
                parallelism,
            )
            completed = 0
            active_batch: list[Chunk] = []
            in_flight_chunks: list[Chunk] = []
            for active_batch in _batches(pending_chunks, parallelism):
                in_flight_chunks = list(active_batch)
                for chunk in active_batch:
                    await _ensure_running_run(db, document, chunk, metadata)
                await db.commit()
                extracted, extraction_error = await _extract_batch(
                    active_batch, selected_extractor, parallelism, contexts
                )
                for item in extracted:
                    await _persist_chunk_result(
                        db,
                        document,
                        item.chunk,
                        item.extraction,
                        metadata,
                        persist_relations=not settings.graph_document_consolidation_enabled,
                    )
                    completed += 1
                    # Successfully persisted; remove from in-flight tracking.
                    in_flight_chunks = [c for c in in_flight_chunks if c.id != item.chunk.id]
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
                in_flight_chunks = []
            if settings.graph_document_consolidation_enabled:
                if on_batch_committed is not None:
                    await on_batch_committed()
                await consolidate_document(db, document, chunks, metadata)
                await db.commit()
                if on_batch_committed is not None:
                    await on_batch_committed()
            await refresh_dataset_analytics(db, document.project_id, document.dataset_id)
            await db.commit()
            logger.info("graph analytics refreshed dataset=%s", document.dataset_id)
            return document.id
        except Exception as exc:
            # Rollback expires ORM attributes. Snapshot primitives before rollback so
            # failure bookkeeping never performs implicit async IO from sync access.
            failed_chunks = [(chunk.id, chunk.text) for chunk in in_flight_chunks]
            await db.rollback()
            for chunk_id, chunk_text in failed_chunks:
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


async def _chunk_run_succeeded(db: AsyncSession, chunk: Chunk, metadata: ExtractorMetadata) -> bool:
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
    chunks: list[Chunk],
    extractor: Extractor,
    parallelism: int,
    contexts: dict[str, ChunkExtractionContext] | None = None,
) -> tuple[list[ChunkExtractionResult], BaseException | None]:
    selected_contexts = contexts or {
        chunk.id: ChunkExtractionContext(
            "", (), None, chunk.chunk_index, len(chunks), "", chunk.text, ""
        )
        for chunk in chunks
    }
    if parallelism <= 1:
        results: list[ChunkExtractionResult] = []
        for chunk in chunks:
            try:
                results.append(
                    ChunkExtractionResult(
                        chunk, _extract_one(extractor, selected_contexts[chunk.id])
                    )
                )
            except BaseException as exc:
                return results, exc
        return results, None
    semaphore = Semaphore(parallelism)

    async def run(chunk: Chunk) -> ChunkExtractionResult:
        async with semaphore:
            return ChunkExtractionResult(
                chunk, await to_thread(_extract_one, extractor, selected_contexts[chunk.id])
            )

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
    persist_relations: bool = True,
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
    run.raw_extraction = result.model_dump(mode="json")
    now = datetime.now(UTC)
    entities: dict[str, list[CanonicalEntity]] = {}
    for entity_item in result.entities:
        offset = chunk.text.find(entity_item.name)
        if offset < 0:
            logger.warning(
                "skipping entity without exact evidence document=%s chunk=%s entity=%r",
                document.id,
                chunk.id,
                entity_item.name,
            )
            continue
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
                valid_from=now,
                valid_until=None,
            )
            db.add(entity)
        elif entity.valid_until is not None:
            entity.valid_until = None
            entity.valid_from = now
            entity.superseded_by = None
        entities.setdefault(normalized, []).append(entity)
        evidence_id = stable_id("ev", run_id, entity_id)
        if await db.get(GraphEvidence, evidence_id) is None:
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
                    start_offset=offset,
                    end_offset=offset + len(entity_item.name),
                    confidence=entity_item.confidence,
                )
            )
    await db.flush()
    if not persist_relations:
        run.status, run.error_message, run.completed_at = (
            RunStatus.SUCCEEDED,
            None,
            datetime.now(UTC),
        )
        return
    for relation_item in result.relations:
        source_matches = entities.get(normalize_name(relation_item.source), [])
        target_matches = entities.get(normalize_name(relation_item.target), [])
        if relation_item.source_type is not None:
            source_matches = [
                item
                for item in source_matches
                if normalize_name(item.entity_type)
                == normalize_name(relation_item.source_type or "")
            ]
        if relation_item.target_type is not None:
            target_matches = [
                item
                for item in target_matches
                if normalize_name(item.entity_type)
                == normalize_name(relation_item.target_type or "")
            ]
        source = source_matches[0] if len(source_matches) == 1 else None
        target = target_matches[0] if len(target_matches) == 1 else None
        if source is None or target is None or source.id == target.id:
            continue
        quote = relation_item.quote or chunk.text
        quote_offset = chunk.text.find(quote)
        if not quote or quote_offset < 0:
            logger.warning(
                "skipping relation without exact evidence document=%s chunk=%s type=%r",
                document.id,
                chunk.id,
                relation_item.type,
            )
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
                valid_from=now,
                valid_until=None,
            )
            db.add(relation)
        elif relation.valid_until is not None:
            relation.valid_until = None
            relation.valid_from = now
            relation.superseded_by = None
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
                    quote=quote,
                    start_offset=quote_offset,
                    end_offset=quote_offset + len(quote),
                    confidence=relation_item.confidence,
                )
            )
    run.status, run.error_message, run.completed_at = RunStatus.SUCCEEDED, None, datetime.now(UTC)


async def consolidate_document(
    db: AsyncSession, document: Document, chunks: list[Chunk], metadata: ExtractorMetadata
) -> None:
    if not chunks:
        return
    raw_runs = list(
        await db.scalars(
            select(GraphExtractionRun).where(
                GraphExtractionRun.document_id == document.id,
                GraphExtractionRun.extractor_version == metadata.extractor_version,
                GraphExtractionRun.status == RunStatus.SUCCEEDED,
            )
        )
    )
    raw = {run.chunk_id: run.raw_extraction for run in raw_runs if run.raw_extraction is not None}
    if set(raw) != {chunk.id for chunk in chunks}:
        raise ValueError(
            "document consolidation requires successful raw extraction for every chunk"
        )
    input_data = build_input(chunks, raw)
    settings = get_settings()
    input_chars = len(json.dumps(input_data.payload, separators=(",", ":"), ensure_ascii=False))
    if input_chars > settings.graph_document_consolidation_max_chars:
        raise ValueError("document consolidation input exceeds configured character limit")
    run_id = stable_id(
        "con",
        document.id,
        input_data.snapshot_hash,
        metadata.extractor_version,
        settings.graph_document_consolidation_version,
    )
    run = await db.get(GraphConsolidationRun, run_id)
    if run is not None and run.status == RunStatus.SUCCEEDED and run.output is not None:
        output = ConsolidationOutput.model_validate(run.output)
    else:
        if run is None:
            run = GraphConsolidationRun(
                id=run_id,
                project_id=document.project_id,
                dataset_id=document.dataset_id,
                document_id=document.id,
                snapshot_hash=input_data.snapshot_hash,
                extractor_version=metadata.extractor_version,
                consolidation_version=settings.graph_document_consolidation_version,
                prompt_version=settings.graph_document_consolidation_prompt_version,
                status=RunStatus.RUNNING,
            )
            db.add(run)
        else:
            run.status, run.error_message, run.completed_at = RunStatus.RUNNING, None, None
        await db.flush()
        try:
            output = await to_thread(
                consolidate_openai,
                settings.graph_extractor_base_url,
                settings.openai_api_key.get_secret_value(),
                settings.graph_extractor_model,
                settings.graph_document_consolidation_prompt_version,
                input_data.payload,
                settings.graph_extractor_timeout_seconds,
            )
            run.output = output.model_dump(mode="json")
        except Exception as exc:
            run.status, run.error_message, run.completed_at = (
                RunStatus.FAILED,
                sanitized_error(exc),
                datetime.now(UTC),
            )
            await db.commit()
            raise
        try:
            validate_output(output, {chunk.id: chunk for chunk in chunks})
        except Exception as exc:
            run.status, run.error_message, run.completed_at = (
                RunStatus.FAILED,
                sanitized_error(exc),
                datetime.now(UTC),
            )
            await db.commit()
            raise
        run.status, run.error_message, run.completed_at = (
            RunStatus.SUCCEEDED,
            None,
            datetime.now(UTC),
        )
        # Checkpoint provider output before graph persistence and external projection.
        await db.commit()
    await _persist_consolidation_output(db, document, output, run_id, metadata)


async def _persist_consolidation_output(
    db: AsyncSession,
    document: Document,
    output: ConsolidationOutput,
    run_id: str,
    metadata: ExtractorMetadata,
) -> None:
    entities = list(
        await db.scalars(
            select(CanonicalEntity).where(
                CanonicalEntity.project_id == document.project_id,
                CanonicalEntity.dataset_id == document.dataset_id,
            )
        )
    )
    document_entity_ids = set(
        await db.scalars(
            select(GraphEvidence.entity_id).where(
                GraphEvidence.project_id == document.project_id,
                GraphEvidence.dataset_id == document.dataset_id,
                GraphEvidence.document_id == document.id,
                GraphEvidence.entity_id.is_not(None),
            )
        )
    )
    by_key = {
        (normalize_name(item.canonical_name), normalize_name(item.entity_type)): item
        for item in entities
        if item.id in document_entity_ids
    }
    for relation_item in output.relations:
        source = by_key.get(
            (normalize_name(relation_item.source), normalize_name(relation_item.source_type))
        )
        target = by_key.get(
            (normalize_name(relation_item.target), normalize_name(relation_item.target_type))
        )
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
                review_state=ReviewState.NEEDS_REVIEW,
                valid_from=datetime.now(UTC),
                valid_until=None,
            )
            db.add(relation)
        elif relation.valid_until is not None:
            relation.valid_until = None
            relation.valid_from = datetime.now(UTC)
            relation.superseded_by = None
        await _add_consolidation_evidence(
            db,
            document,
            relation_item.evidence_chunk_id,
            relation_item.quote,
            relation_item.confidence,
            run_id,
            relation_id=relation_id,
        )
    for alias_item in output.aliases:
        entity = by_key.get(
            (normalize_name(alias_item.canonical_name), normalize_name(alias_item.entity_type))
        )
        if entity is None or normalize_name(alias_item.alias) == normalize_name(
            entity.canonical_name
        ):
            continue
        alias_id = stable_id(
            "alias",
            document.dataset_id,
            entity.id,
            normalize_name(alias_item.alias),
            normalize_name(alias_item.entity_type),
        )
        alias = await db.scalar(
            select(EntityAlias).where(
                EntityAlias.project_id == document.project_id,
                EntityAlias.dataset_id == document.dataset_id,
                EntityAlias.normalized_alias == normalize_name(alias_item.alias),
                EntityAlias.entity_type == alias_item.entity_type,
            )
        )
        if alias is None:
            alias = EntityAlias(
                id=alias_id,
                project_id=document.project_id,
                dataset_id=document.dataset_id,
                entity_id=entity.id,
                alias=alias_item.alias,
                normalized_alias=normalize_name(alias_item.alias),
                entity_type=alias_item.entity_type,
                confidence=alias_item.confidence,
            )
            db.add(alias)
        elif alias.entity_id != entity.id:
            raise ValueError("ambiguous exact alias maps to multiple canonical entities")
        evidence_id = await _add_consolidation_evidence(
            db,
            document,
            alias_item.evidence_chunk_id,
            alias_item.quote,
            alias_item.confidence,
            run_id,
            entity_id=entity.id,
        )
        association = await db.get(EntityAliasEvidence, (alias.id, evidence_id))
        if alias.entity_id == entity.id and association is None:
            db.add(EntityAliasEvidence(alias_id=alias.id, evidence_id=evidence_id))


async def _add_consolidation_evidence(
    db: AsyncSession,
    document: Document,
    chunk_id: str,
    quote: str,
    confidence: float,
    run_id: str,
    entity_id: str | None = None,
    relation_id: str | None = None,
) -> str:
    chunk = await db.get(Chunk, chunk_id)
    if (
        chunk is None
        or chunk.project_id != document.project_id
        or chunk.dataset_id != document.dataset_id
        or chunk.document_id != document.id
        or quote not in chunk.text
    ):
        raise ValueError("consolidation evidence is invalid")
    evidence_id = stable_id("ev", run_id, entity_id or relation_id or "", chunk_id, quote)
    extraction_run_id = await db.scalar(
        select(GraphExtractionRun.id).where(
            GraphExtractionRun.document_id == document.id,
            GraphExtractionRun.chunk_id == chunk_id,
            GraphExtractionRun.status == RunStatus.SUCCEEDED,
        )
    )
    if extraction_run_id is None:
        raise ValueError("consolidation evidence has no successful extraction run")
    if await db.get(GraphEvidence, evidence_id) is None:
        start = chunk.text.find(quote)
        db.add(
            GraphEvidence(
                id=evidence_id,
                project_id=document.project_id,
                dataset_id=document.dataset_id,
                document_id=document.id,
                chunk_id=chunk_id,
                run_id=extraction_run_id,
                entity_id=entity_id,
                relation_id=relation_id,
                quote=quote,
                start_offset=start,
                end_offset=start + len(quote),
                confidence=confidence,
            )
        )
    return evidence_id
