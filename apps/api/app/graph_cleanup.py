"""Durable cleanup tracking after authoritative deletion."""

from datetime import UTC, datetime

from open_graph_core.extraction import stable_id
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph_models import GraphCleanupOutbox, GraphCleanupTarget
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
    """Mark the retained deletion audit record complete after PostgreSQL cleanup."""
    cleanup.ready, cleanup.completed_at = True, datetime.now(UTC)
    cleanup.published_at, cleanup.lease_expires_at = None, None
    cleanup.execution_lease_expires_at, cleanup.next_attempt_at = None, None
    cleanup.dead_lettered_at, cleanup.last_error = None, None
