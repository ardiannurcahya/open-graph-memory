"""Authoritative extraction persistence followed by rebuildable Neo4j projection."""

import hashlib
from datetime import UTC, datetime

from open_graph_core.extraction import DeterministicExtractor, Extractor, normalize_name, stable_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db import engine
from app.graph_models import (
    CanonicalEntity,
    GraphEvidence,
    GraphExtractionRun,
    RelationAssertion,
    ReviewState,
    RunStatus,
)
from app.graph_store import (
    DocumentProjection,
    EvidenceProjection,
    GraphProjection,
    GraphStore,
    Neo4jGraphStore,
    RelationProjection,
)
from app.ingestion import sanitized_error
from app.models import Chunk, Document, DocumentStatus

EXTRACTOR_VERSION = "graph-extractor-v1"
PROMPT_VERSION = "graph-v1"


def _store() -> GraphStore:
    settings = get_settings()
    return Neo4jGraphStore(settings.neo4j_url, settings.neo4j_auth.get_secret_value())


async def extract_document(
    document_id: str, extractor: Extractor | None = None, graph: GraphStore | None = None
) -> str:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        document = await db.get(Document, document_id)
        if document is None or document.status != DocumentStatus.INDEXED:
            raise ValueError("graph extraction requires an indexed document")
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
            for chunk in chunks:
                await _persist_chunk(db, document, chunk, extractor or DeterministicExtractor())
            await db.commit()
            await project_document(db, document, graph or _store())
            return document.id
        except BaseException as exc:
            await db.rollback()
            for chunk in chunks:
                run_id = stable_id("run", chunk.id, EXTRACTOR_VERSION, _hash(chunk.text))
                run = await db.get(GraphExtractionRun, run_id)
                if run is not None and run.status != RunStatus.SUCCEEDED:
                    run.status = RunStatus.FAILED
                    run.error_message = sanitized_error(exc)
                    run.completed_at = datetime.now(UTC)
            await db.commit()
            raise


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def _persist_chunk(
    db: AsyncSession, document: Document, chunk: Chunk, extractor: Extractor
) -> None:
    input_hash = _hash(chunk.text)
    run_id = stable_id("run", chunk.id, EXTRACTOR_VERSION, input_hash)
    run = await db.get(GraphExtractionRun, run_id)
    if run is not None and run.status == RunStatus.SUCCEEDED:
        return
    if run is None:
        run = GraphExtractionRun(
            id=run_id,
            project_id=document.project_id,
            dataset_id=document.dataset_id,
            document_id=document.id,
            chunk_id=chunk.id,
            status=RunStatus.RUNNING,
            provider="deterministic",
            model="deterministic-graph-v1",
            extractor_version=EXTRACTOR_VERSION,
            prompt_version=PROMPT_VERSION,
            ontology_version=None,
            input_hash=input_hash,
        )
        db.add(run)
        await db.flush()
    else:
        run.status = RunStatus.RUNNING
        run.error_message = None
        run.completed_at = None
    # Keep the attempt record if provider extraction fails.
    await db.commit()
    result = extractor.extract(chunk.text)
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
            EXTRACTOR_VERSION,
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
                extractor_version=EXTRACTOR_VERSION,
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
    await graph.bootstrap()
    await graph.project_document(
        DocumentProjection(
            project_id=str(document.project_id),
            dataset_id=document.dataset_id,
            document_id=document.id,
            chunk_ids=tuple(chunk.id for chunk in chunks),
            entities=tuple(
                GraphProjection(
                    str(e.project_id),
                    e.dataset_id,
                    e.id,
                    e.canonical_name,
                    e.entity_type,
                    e.version,
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
