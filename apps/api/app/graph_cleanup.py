"""Durable cleanup of Neo4j projections after authoritative deletion."""

from datetime import UTC, datetime

from open_graph_core.extraction import stable_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import engine
from app.graph_models import GraphCleanupOutbox, GraphCleanupTarget
from app.graph_pipeline import _store
from app.ingestion import sanitized_error
from app.models import Dataset, Document


async def create_document_cleanup(db: AsyncSession, document: Document) -> GraphCleanupOutbox:
    cleanup_id = stable_id(
        "graph-cleanup-document", str(document.project_id), document.dataset_id, document.id
    )
    cleanup = await db.get(GraphCleanupOutbox, cleanup_id)
    if cleanup is None:
        cleanup = GraphCleanupOutbox(
            id=cleanup_id,
            project_id=document.project_id,
            dataset_id=document.dataset_id,
            document_id=document.id,
            target=GraphCleanupTarget.DOCUMENT,
        )
        db.add(cleanup)
    return cleanup


async def create_dataset_cleanup(db: AsyncSession, dataset: Dataset) -> GraphCleanupOutbox:
    cleanup_id = stable_id("graph-cleanup-dataset", str(dataset.project_id), dataset.id)
    cleanup = await db.get(GraphCleanupOutbox, cleanup_id)
    if cleanup is None:
        cleanup = GraphCleanupOutbox(
            id=cleanup_id,
            project_id=dataset.project_id,
            dataset_id=dataset.id,
            target=GraphCleanupTarget.DATASET,
        )
        db.add(cleanup)
    return cleanup


async def mark_cleanup_ready(db: AsyncSession, cleanup: GraphCleanupOutbox) -> None:
    # This is committed with the authoritative row deletion, never before it.
    cleanup.ready, cleanup.published_at, cleanup.last_error = True, None, None


async def dispatch_pending_graph_cleanup(limit: int = 100) -> int:
    from app.worker import celery_app

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        rows = list(
            await db.scalars(
                select(GraphCleanupOutbox)
                .where(
                    GraphCleanupOutbox.ready.is_(True),
                    GraphCleanupOutbox.completed_at.is_(None),
                    GraphCleanupOutbox.published_at.is_(None),
                )
                .order_by(GraphCleanupOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        sent = 0
        for row in rows:
            row.attempts += 1
            try:
                celery_app.send_task("graph.cleanup_projection", args=[row.id])
            except Exception as exc:
                row.last_error = sanitized_error(exc)
            else:
                row.published_at, row.last_error = datetime.now(UTC), None
                sent += 1
        await db.commit()
    return sent


async def execute_graph_cleanup(cleanup_id: str) -> str:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        cleanup = await db.scalar(
            select(GraphCleanupOutbox).where(GraphCleanupOutbox.id == cleanup_id).with_for_update()
        )
        if cleanup is None or cleanup.completed_at is not None or not cleanup.ready:
            return cleanup_id
        project_id, dataset_id, document_id, target = (
            str(cleanup.project_id),
            cleanup.dataset_id,
            cleanup.document_id,
            cleanup.target,
        )
    try:
        graph = _store()
        if target == GraphCleanupTarget.DATASET:
            await graph.reconcile_dataset(project_id, dataset_id)
        elif document_id is not None:
            await graph.delete_document(project_id, dataset_id, document_id)
        else:
            raise ValueError("document graph cleanup is missing document_id")
    except BaseException as exc:
        async with factory() as db:
            cleanup = await db.get(GraphCleanupOutbox, cleanup_id)
            if cleanup is not None and cleanup.completed_at is None:
                cleanup.published_at, cleanup.last_error = None, sanitized_error(exc)
                await db.commit()
        raise
    async with factory() as db:
        cleanup = await db.get(GraphCleanupOutbox, cleanup_id)
        if cleanup is not None:
            cleanup.completed_at, cleanup.last_error = datetime.now(UTC), None
            await db.commit()
    return cleanup_id
