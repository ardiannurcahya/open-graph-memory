"""ARQ worker configuration with durable PostgreSQL-backed dispatch."""

import asyncio
import logging
import random
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

import arq
from arq import Retry, func
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
MAX_INDEXING_OUTBOX_ATTEMPTS = 20
INDEXING_TRANSIENT_ERRORS = (TimeoutError, ConnectionError, OSError)


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def create_redis_pool() -> ArqRedis:
    return await arq.create_pool(redis_settings())


# --- Tasks ---

async def task_index_document(ctx: dict[str, Any], job_id: str) -> str:
    from app.ingestion import run_ingestion

    heartbeat = asyncio.create_task(_indexing_heartbeat(job_id))
    try:
        return await run_ingestion(job_id)
    except asyncio.CancelledError:
        await asyncio.shield(_requeue_indexing_job(job_id, "worker execution cancelled"))
        raise
    except INDEXING_TRANSIENT_ERRORS as exc:
        job_try = int(ctx.get("job_try", 1))
        if job_try >= 5:
            raise
        await _requeue_indexing_job(job_id, f"transient failure: {type(exc).__name__}")
        raise Retry(defer=min(60, 2**job_try) + random.random()) from exc
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def task_extract_graph(ctx: dict[str, Any], job_id: str) -> str:
    from app.graph_dispatch import execute_graph_job, renew_graph_job_lease

    heartbeat = asyncio.create_task(
        _heartbeat(
            lambda: renew_graph_job_lease(job_id),
            max(30, int(settings.graph_extractor_timeout_seconds) // 3),
        )
    )
    try:
        return await execute_graph_job(job_id)
    except asyncio.CancelledError:
        from app.graph_dispatch import requeue_graph_job

        await asyncio.shield(requeue_graph_job(job_id, "worker execution cancelled"))
        raise
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat


async def task_dispatch_indexing_outbox(ctx: dict[str, Any]) -> int:
    return await _dispatch_pending_indexing(ctx["redis"])


async def task_reconcile_indexing_jobs(ctx: dict[str, Any]) -> int:
    return await _reconcile_indexing_jobs()


async def task_dispatch_graph_outbox(ctx: dict[str, Any]) -> int:
    from app.graph_dispatch import dispatch_pending_graph_jobs

    return await dispatch_pending_graph_jobs(ctx["redis"])


async def task_reconcile_graph_jobs(ctx: dict[str, Any]) -> int:
    from app.graph_dispatch import reconcile_graph_jobs

    return await reconcile_graph_jobs()


async def _heartbeat(callback: Any, interval: int) -> None:
    while True:
        await asyncio.sleep(interval)
        await callback()


async def _indexing_heartbeat(job_id: str) -> None:
    from sqlalchemy import update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import engine
    from app.models import IndexingJob, JobStatus

    interval = max(30, settings.indexing_stale_seconds // 3)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    while True:
        await asyncio.sleep(interval)
        async with factory() as db:
            await db.execute(
                update(IndexingJob)
                .where(IndexingJob.id == job_id, IndexingJob.status == JobStatus.RUNNING)
                .values(updated_at=datetime.now(UTC))
            )
            await db.commit()


async def _maintenance_loop(redis: ArqRedis) -> None:
    from app.graph_dispatch import dispatch_pending_graph_jobs, reconcile_graph_jobs

    while True:
        try:
            await _dispatch_pending_indexing(redis)
            await _reconcile_indexing_jobs()
            await dispatch_pending_graph_jobs(redis)
            await reconcile_graph_jobs()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("ARQ maintenance poll failed; durable work will be retried")
        await asyncio.sleep(settings.outbox_poll_seconds)


async def startup(ctx: dict[str, Any]) -> None:
    ctx["maintenance_task"] = asyncio.create_task(_maintenance_loop(ctx["redis"]))


async def shutdown(ctx: dict[str, Any]) -> None:
    task = ctx.get("maintenance_task")
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


# --- Helpers ---

async def _dispatch_pending_indexing(redis: ArqRedis, limit: int = 100) -> int:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import engine
    from app.ingestion import sanitized_error
    from app.models import Document, DocumentStatus, IndexingJob, IndexingOutbox, JobStatus

    sent = 0
    claimed_at = datetime.now(UTC)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        rows = list(
            await db.scalars(
                select(IndexingOutbox)
                .join(IndexingJob, IndexingJob.id == IndexingOutbox.job_id)
                .where(
                    IndexingOutbox.dispatched_at.is_(None),
                    IndexingOutbox.attempts < MAX_INDEXING_OUTBOX_ATTEMPTS,
                    IndexingJob.status == JobStatus.QUEUED,
                )
                .order_by(IndexingOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.attempts += 1
            row.dispatched_at = claimed_at
            row.last_error = None
        await db.commit()

    for row in rows:
        try:
            await redis.enqueue_job(
                "task_index_document", row.job_id, _job_id=f"index:{row.job_id}"
            )
        except Exception as exc:
            message = sanitized_error(exc)
            async with factory() as db:
                outbox = await db.get(IndexingOutbox, row.job_id)
                job = await db.get(IndexingJob, row.job_id)
                if outbox is not None and outbox.dispatched_at == claimed_at:
                    outbox.dispatched_at = None
                    outbox.last_error = message
                    if outbox.attempts >= MAX_INDEXING_OUTBOX_ATTEMPTS and job is not None:
                        job.status = JobStatus.FAILED
                        job.error_code = "DispatchError"
                        job.error_message = message
                        document = await db.get(Document, job.document_id)
                        if document is not None:
                            document.status = DocumentStatus.FAILED
                            document.error_message = message
                await db.commit()
        else:
            sent += 1
    return sent


async def _requeue_indexing_job(job_id: str, reason: str) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import engine
    from app.models import IndexingJob, IndexingOutbox, JobStatus

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        job = await db.get(IndexingJob, job_id, with_for_update=True)
        if job is None or job.status == JobStatus.SUCCEEDED:
            return
        job.status = JobStatus.QUEUED
        job.error_message = reason
        outbox = await db.get(IndexingOutbox, job_id)
        if outbox is None:
            db.add(IndexingOutbox(job_id=job_id, attempts=0, last_error=reason))
        else:
            outbox.dispatched_at = None
            outbox.last_error = reason
        await db.commit()


async def _reconcile_indexing_jobs(limit: int = 100) -> int:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import engine
    from app.models import IndexingJob, IndexingOutbox, JobStatus

    cutoff = datetime.now(UTC) - timedelta(seconds=settings.indexing_stale_seconds)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        jobs = list(
            await db.scalars(
                select(IndexingJob)
                .where(IndexingJob.status == JobStatus.RUNNING, IndexingJob.updated_at < cutoff)
                .order_by(IndexingJob.updated_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for job in jobs:
            job.status = JobStatus.QUEUED
            outbox = await db.get(IndexingOutbox, job.id)
            if outbox is None:
                db.add(IndexingOutbox(job_id=job.id, attempts=0))
            else:
                outbox.dispatched_at = None
                outbox.last_error = None
        await db.commit()
        recovered = len(jobs)

        stale_dispatch_cutoff = datetime.now(UTC) - timedelta(
            seconds=settings.indexing_stale_seconds * 2
        )
        stale_outbox = list(
            await db.scalars(
                select(IndexingOutbox)
                .join(IndexingJob, IndexingJob.id == IndexingOutbox.job_id)
                .where(
                    IndexingJob.status == JobStatus.QUEUED,
                    IndexingOutbox.dispatched_at.is_not(None),
                    IndexingOutbox.dispatched_at < stale_dispatch_cutoff,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in stale_outbox:
            row.dispatched_at = None
            row.last_error = "dispatch stale; requeued"
        await db.commit()
        return recovered + len(stale_outbox)


# --- Enqueue helpers (for use by other modules) ---

async def enqueue_index_document(job_id: str) -> None:
    pool = await create_redis_pool()
    try:
        await pool.enqueue_job("task_index_document", job_id, _job_id=f"index:{job_id}")
    finally:
        await pool.close()


async def enqueue_extract_graph(job_id: str) -> None:
    pool = await create_redis_pool()
    try:
        await pool.enqueue_job("task_extract_graph", job_id, _job_id=f"graph:{job_id}")
    finally:
        await pool.close()


# --- Worker settings ---

class WorkerSettings:
    functions = [
        func(task_index_document, timeout=1800, max_tries=5),
        func(
            task_extract_graph,
            timeout=max(3600, int(settings.graph_extractor_timeout_seconds) * 4),
            max_tries=1,
        ),
    ]
    redis_settings = redis_settings()
    max_jobs = 2
    job_timeout = 1800
    keep_result = 0
    max_tries = 1
    health_check_interval = 15
    on_startup = startup
    on_shutdown = shutdown
