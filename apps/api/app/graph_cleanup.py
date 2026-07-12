"""Durable cleanup of Neo4j projections after authoritative deletion."""

from datetime import UTC, datetime, timedelta

from open_graph_core.extraction import stable_id
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import engine
from app.graph_models import GraphCleanupOutbox, GraphCleanupTarget
from app.graph_pipeline import _store
from app.ingestion import sanitized_error
from app.models import Dataset, Document

PUBLISH_LEASE_SECONDS = 300
MAX_PUBLISH_ATTEMPTS = 5


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
    cleanup.ready, cleanup.published_at, cleanup.lease_expires_at = True, None, None
    cleanup.execution_lease_expires_at, cleanup.next_attempt_at = None, datetime.now(UTC)
    cleanup.dead_lettered_at, cleanup.last_error = None, None


async def dispatch_pending_graph_cleanup(limit: int = 100) -> int:
    """Claim delivery rows before publication so a broker-loss window has a finite lease."""
    from app.worker import celery_app

    now = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        rows = list(
            await db.scalars(
                select(GraphCleanupOutbox)
                .where(
                    GraphCleanupOutbox.ready.is_(True),
                    GraphCleanupOutbox.completed_at.is_(None),
                    GraphCleanupOutbox.dead_lettered_at.is_(None),
                    or_(
                        GraphCleanupOutbox.next_attempt_at.is_(None),
                        GraphCleanupOutbox.next_attempt_at <= now,
                    ),
                    or_(
                        GraphCleanupOutbox.lease_expires_at.is_(None),
                        GraphCleanupOutbox.lease_expires_at < now,
                    ),
                )
                .order_by(GraphCleanupOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.attempts += 1
            row.lease_expires_at = now + timedelta(seconds=PUBLISH_LEASE_SECONDS)
        await db.commit()

    claims = {row.id: row.lease_expires_at for row in rows}
    sent = 0
    for row in rows:
        try:
            celery_app.send_task("graph.cleanup_projection", args=[row.id])
        except Exception as exc:
            async with factory() as db:
                claimed = await db.get(GraphCleanupOutbox, row.id)
                if (
                    claimed
                    and claimed.completed_at is None
                    and claimed.lease_expires_at == claims[row.id]
                ):
                    claimed.lease_expires_at = None
                    claimed.last_error = sanitized_error(exc)
                    claimed.next_attempt_at = datetime.now(UTC) + timedelta(
                        seconds=min(60, 2**claimed.attempts)
                    )
                    await db.commit()
        else:
            async with factory() as db:
                claimed = await db.get(GraphCleanupOutbox, row.id)
                if (
                    claimed
                    and claimed.completed_at is None
                    and claimed.lease_expires_at == claims[row.id]
                ):
                    claimed.published_at, claimed.last_error = datetime.now(UTC), None
                    await db.commit()
            sent += 1
    return sent


async def reconcile_graph_cleanup_outbox(limit: int = 100) -> int:
    """Requeue abandoned deliveries and executions; exhausted rows remain observable."""
    now = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        rows = list(
            await db.scalars(
                select(GraphCleanupOutbox)
                .where(
                    GraphCleanupOutbox.ready.is_(True),
                    GraphCleanupOutbox.completed_at.is_(None),
                    GraphCleanupOutbox.dead_lettered_at.is_(None),
                    or_(
                        GraphCleanupOutbox.lease_expires_at < now,
                        GraphCleanupOutbox.execution_lease_expires_at < now,
                    ),
                )
                .order_by(GraphCleanupOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.lease_expires_at, row.execution_lease_expires_at = None, None
            if row.attempts >= MAX_PUBLISH_ATTEMPTS:
                row.dead_lettered_at = now
                row.last_error = "cleanup delivery exhausted retry budget"
            else:
                row.published_at, row.next_attempt_at = None, now
                row.last_error = "cleanup delivery or execution lease expired; requeued"
        await db.commit()
    return len(rows)


async def execute_graph_cleanup(cleanup_id: str) -> str:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as db:
        cleanup = await db.scalar(
            select(GraphCleanupOutbox).where(GraphCleanupOutbox.id == cleanup_id).with_for_update()
        )
        if cleanup is None or cleanup.completed_at is not None or not cleanup.ready:
            return cleanup_id
        if cleanup.execution_lease_expires_at and cleanup.execution_lease_expires_at > now:
            return cleanup_id
        cleanup.execution_lease_expires_at = now + timedelta(seconds=PUBLISH_LEASE_SECONDS)
        project_id, dataset_id, document_id, target = (
            str(cleanup.project_id),
            cleanup.dataset_id,
            cleanup.document_id,
            cleanup.target,
        )
        await db.commit()
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
                cleanup.published_at, cleanup.lease_expires_at = None, None
                cleanup.execution_lease_expires_at = None
                cleanup.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(60, 2**cleanup.attempts)
                )
                cleanup.last_error = sanitized_error(exc)
                await db.commit()
        raise
    async with factory() as db:
        cleanup = await db.get(GraphCleanupOutbox, cleanup_id)
        if cleanup is not None:
            cleanup.completed_at, cleanup.lease_expires_at = datetime.now(UTC), None
            cleanup.execution_lease_expires_at = None
            cleanup.last_error = None
            await db.commit()
    return cleanup_id
