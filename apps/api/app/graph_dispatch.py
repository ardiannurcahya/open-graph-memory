"""Durable graph extraction jobs and PostgreSQL outbox delivery."""

from datetime import UTC, datetime, timedelta

from arq.connections import ArqRedis
from open_graph_core.extraction import stable_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import engine
from app.graph_models import GraphExtractionJob, GraphExtractionOutbox, GraphJobStatus
from app.graph_pipeline import extract_document, extractor_metadata
from app.ingestion import sanitized_error
from app.models import Document, DocumentStatus

LEASE_SECONDS = 300
MAX_GRAPH_OUTBOX_ATTEMPTS = 20


class GraphExtractionFailed(RuntimeError):
    pass


def lease_seconds() -> int:
    from app.config import get_settings

    return max(LEASE_SECONDS, int(get_settings().graph_extractor_timeout_seconds) + 60)


async def enqueue_graph_extraction(db: AsyncSession, document: Document) -> GraphExtractionJob:
    """Persist work atomically with authoritative chunks; publishing is separate."""
    metadata = extractor_metadata()
    job_id = stable_id("graph-job", document.id, metadata.extractor_version)
    job = await db.get(GraphExtractionJob, job_id)
    if job is None:
        job = GraphExtractionJob(
            id=job_id,
            project_id=document.project_id,
            dataset_id=document.dataset_id,
            document_id=document.id,
            status=GraphJobStatus.QUEUED,
            provider=metadata.provider,
            model=metadata.model,
            extractor_version=metadata.extractor_version,
            prompt_version=metadata.prompt_version,
            ontology_version=None,
        )
        db.add(job)
        db.add(GraphExtractionOutbox(job_id=job_id))
    else:
        job.status = GraphJobStatus.QUEUED
        job.attempt = 0
        job.error_message = None
        job.next_attempt_at = datetime.now(UTC)
        outbox = await db.get(GraphExtractionOutbox, job_id)
        if outbox is None:
            db.add(GraphExtractionOutbox(job_id=job_id))
        else:
            outbox.published_at = None
            outbox.last_error = None
    document.graph_stage = "queued"
    return job


async def dispatch_pending_graph_jobs(redis: ArqRedis | None = None, limit: int = 100) -> int:
    now, sent = datetime.now(UTC), 0
    owns_pool = redis is None
    if redis is None:
        from app.arq_worker import create_redis_pool

        redis = await create_redis_pool()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            rows = list(
                await db.scalars(
                    select(GraphExtractionOutbox)
                    .join(GraphExtractionJob)
                    .where(
                        GraphExtractionOutbox.published_at.is_(None),
                        GraphExtractionOutbox.attempts < MAX_GRAPH_OUTBOX_ATTEMPTS,
                        GraphExtractionJob.status == GraphJobStatus.QUEUED,
                        GraphExtractionJob.next_attempt_at <= now,
                    )
                    .order_by(GraphExtractionOutbox.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for row in rows:
                row.attempts += 1
                row.published_at = now
                row.last_error = None
            await db.commit()

        for row in rows:
            try:
                await redis.enqueue_job(
                    "task_extract_graph", row.job_id, _job_id=f"graph:{row.job_id}"
                )
            except Exception as exc:
                message = sanitized_error(exc)
                async with factory() as db:
                    outbox = await db.get(GraphExtractionOutbox, row.job_id)
                    job = await db.get(GraphExtractionJob, row.job_id)
                    if outbox is not None and outbox.published_at == now:
                        outbox.published_at = None
                        outbox.last_error = message
                        if outbox.attempts >= MAX_GRAPH_OUTBOX_ATTEMPTS and job is not None:
                            job.status = GraphJobStatus.FAILED
                            job.error_message = message
                            document = await db.get(Document, job.document_id)
                            if document is not None:
                                document.status = DocumentStatus.FAILED
                                document.graph_stage = "failed"
                                document.error_message = message
                    await db.commit()
            else:
                sent += 1
        return sent
    finally:
        if owns_pool:
            await redis.close()


async def reconcile_graph_jobs(limit: int = 100) -> int:
    now = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        # Recover RUNNING jobs with expired leases.
        jobs = list(
            await db.scalars(
                select(GraphExtractionJob)
                .where(
                    GraphExtractionJob.status == GraphJobStatus.RUNNING,
                    GraphExtractionJob.lease_expires_at < now,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for job in jobs:
            job.status, job.lease_expires_at, job.next_attempt_at = GraphJobStatus.QUEUED, None, now
            outbox = await db.get(GraphExtractionOutbox, job.id)
            if outbox:
                outbox.published_at = None
        await db.commit()
        recovered = len(jobs)

        # Recover QUEUED jobs whose outbox was dispatched but the task was lost.
        stale_cutoff = now - timedelta(seconds=lease_seconds() * 2)
        stale_outbox = list(
            await db.scalars(
                select(GraphExtractionOutbox)
                .join(GraphExtractionJob)
                .where(
                    GraphExtractionOutbox.published_at.is_not(None),
                    GraphExtractionJob.status == GraphJobStatus.QUEUED,
                    GraphExtractionOutbox.published_at < stale_cutoff,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in stale_outbox:
            row.published_at = None
            row.last_error = "dispatch stale; requeued"
        await db.commit()
        return recovered + len(stale_outbox)


async def renew_graph_job_lease(job_id: str) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        job = await db.scalar(
            select(GraphExtractionJob).where(GraphExtractionJob.id == job_id).with_for_update()
        )
        if job is not None and job.status == GraphJobStatus.RUNNING:
            job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds())
            await db.commit()


async def requeue_graph_job(job_id: str, reason: str) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        job = await db.get(GraphExtractionJob, job_id, with_for_update=True)
        if job is None or job.status == GraphJobStatus.SUCCEEDED:
            return
        job.status = GraphJobStatus.QUEUED
        job.lease_expires_at = None
        job.next_attempt_at = datetime.now(UTC)
        job.error_message = reason
        outbox = await db.get(GraphExtractionOutbox, job_id)
        if outbox is None:
            db.add(GraphExtractionOutbox(job_id=job_id, last_error=reason))
        else:
            outbox.published_at = None
            outbox.last_error = reason
        await db.commit()


async def execute_graph_job(job_id: str) -> str:
    now = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        job = await db.scalar(
            select(GraphExtractionJob).where(GraphExtractionJob.id == job_id).with_for_update()
        )
        if job is None:
            return job_id
        if job.status == GraphJobStatus.SUCCEEDED or (
            job.status == GraphJobStatus.RUNNING
            and job.lease_expires_at
            and job.lease_expires_at > now
        ):
            return job.document_id
        if job.attempt >= job.max_attempts:
            job.status, job.lease_expires_at = GraphJobStatus.FAILED, None
            await db.commit()
            return job.document_id
        document = await db.get(Document, job.document_id)
        if (
            document is None
            or document.project_id != job.project_id
            or document.dataset_id != job.dataset_id
        ):
            raise ValueError("graph job document scope mismatch")
        if document.status not in {DocumentStatus.INDEXED, DocumentStatus.PERSISTING}:
            raise ValueError("graph extraction requires a persisted document")
        job.status, job.attempt = GraphJobStatus.RUNNING, job.attempt + 1
        job.lease_expires_at, job.error_message, document.graph_stage = (
            now + timedelta(seconds=lease_seconds()),
            None,
            "extracting",
        )
        await db.commit()
    try:
        await extract_document(
            job.document_id,
            on_batch_committed=lambda: renew_graph_job_lease(job_id),
        )
    except Exception as exc:
        message = sanitized_error(exc)
        async with factory() as db:
            job = await db.get(GraphExtractionJob, job_id)
            document = await db.get(Document, job.document_id) if job else None
            if job is None:
                raise
            job.error_message, job.lease_expires_at = message, None
            if job.attempt >= job.max_attempts:
                job.status = GraphJobStatus.FAILED
                if document:
                    document.status, document.graph_stage, document.error_message = (
                        DocumentStatus.FAILED,
                        "failed",
                        message,
                    )
            else:
                job.status = GraphJobStatus.QUEUED
                job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=min(60, 2**job.attempt))
                outbox = await db.get(GraphExtractionOutbox, job.id)
                if outbox:
                    outbox.published_at = None
            await db.commit()
        raise GraphExtractionFailed(f"graph extraction failed for job {job_id}: {message}") from exc
    async with factory() as db:
        job = await db.get(GraphExtractionJob, job_id)
        if job:
            document = await db.get(Document, job.document_id)
            job.status, job.lease_expires_at, job.error_message = (
                GraphJobStatus.SUCCEEDED,
                None,
                None,
            )
            if document:
                document.status, document.graph_stage, document.error_message = (
                    DocumentStatus.INDEXED,
                    "complete",
                    None,
                )
            await db.commit()
    return job_id
