"""Durable graph extraction jobs and PostgreSQL outbox delivery."""

from datetime import UTC, datetime, timedelta

from open_graph_core.extraction import stable_id
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import engine
from app.graph_models import GraphExtractionJob, GraphExtractionOutbox, GraphJobStatus
from app.graph_pipeline import extract_document, extractor_metadata
from app.ingestion import sanitized_error
from app.models import Document, DocumentStatus

LEASE_SECONDS = 300


class GraphExtractionFailed(RuntimeError):
    pass


def lease_seconds() -> int:
    from app.config import get_settings

    return max(LEASE_SECONDS, int(get_settings().graph_extractor_timeout_seconds) + 60)


async def enqueue_graph_extraction(db: AsyncSession, document: Document) -> GraphExtractionJob:
    """Persist work atomically with successful vector indexing; publishing is separate."""
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
    document.graph_stage = "queued"
    return job


async def dispatch_pending_graph_jobs(limit: int = 100) -> int:
    from app.worker import celery_app

    now, sent = datetime.now(UTC), 0
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        rows = list(
            await db.scalars(
                select(GraphExtractionOutbox)
                .join(GraphExtractionJob)
                .where(
                    GraphExtractionOutbox.published_at.is_(None),
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
            try:
                celery_app.send_task("graph.extract_job", args=[row.job_id])
            except Exception as exc:
                row.last_error = sanitized_error(exc)
            else:
                row.published_at, row.last_error = now, None
                sent += 1
        await db.commit()
    return sent


async def reconcile_graph_jobs(limit: int = 100) -> int:
    now = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
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
    return len(jobs)


async def execute_graph_job(job_id: str) -> str:
    now = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        job = await db.scalar(
            select(GraphExtractionJob).where(GraphExtractionJob.id == job_id).with_for_update()
        )
        if job is None:
            raise ValueError("graph extraction job not found")
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
        if document.status != DocumentStatus.INDEXED:
            raise ValueError("graph extraction requires an indexed document")
        job.status, job.attempt = GraphJobStatus.RUNNING, job.attempt + 1
        job.lease_expires_at, job.error_message, document.graph_stage = (
            now + timedelta(seconds=lease_seconds()),
            None,
            "extracting",
        )
        await db.commit()
    try:
        await extract_document(job.document_id)
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
                    document.graph_stage = "failed"
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
                document.graph_stage = "complete"
            await db.commit()
    return job_id
