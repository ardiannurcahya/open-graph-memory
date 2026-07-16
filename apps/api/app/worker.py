from datetime import UTC, datetime, timedelta

from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded

from app.async_runner import runner
from app.config import get_settings

settings = get_settings()
task_soft_time_limit = max(270, int(settings.graph_extractor_timeout_seconds) + 90)
task_time_limit = task_soft_time_limit + 30
celery_app = Celery("opengraphrag", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=task_soft_time_limit,
    task_time_limit=task_time_limit,
    task_reject_on_worker_lost=True,
    task_default_queue="default",
    task_routes={
        "graph.extract_job": {"queue": "graph"},
        "graph.cleanup_projection": {"queue": "graph"},
    },
    beat_schedule={
        "dispatch-indexing-outbox": {
            "task": "ingestion.dispatch_outbox",
            "schedule": settings.outbox_poll_seconds,
        },
        "reconcile-indexing-jobs": {
            "task": "ingestion.reconcile_jobs",
            "schedule": settings.outbox_poll_seconds,
        },
        "dispatch-graph-extraction-outbox": {
            "task": "graph.dispatch_outbox",
            "schedule": settings.outbox_poll_seconds,
        },
        "reconcile-graph-extraction-jobs": {
            "task": "graph.reconcile_jobs",
            "schedule": settings.outbox_poll_seconds,
        },
        "dispatch-graph-cleanup-outbox": {
            "task": "graph.dispatch_cleanup_outbox",
            "schedule": settings.outbox_poll_seconds,
        },
        "reconcile-graph-cleanup-outbox": {
            "task": "graph.reconcile_cleanup_outbox",
            "schedule": settings.outbox_poll_seconds,
        },
    },
)


@celery_app.task(name="foundation.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"


@celery_app.task(
    bind=True,
    name="ingestion.index_document",
    autoretry_for=(TimeoutError, ConnectionError, OSError, SoftTimeLimitExceeded),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=4,
)  # type: ignore[untyped-decorator]
def index_document(self: object, job_id: str) -> str:
    from app.ingestion import execute

    return execute(job_id)


@celery_app.task(name="graph.extract_job")  # type: ignore[untyped-decorator]
def extract_graph(job_id: str) -> str:
    from app.graph_dispatch import execute_graph_job

    return runner.run(execute_graph_job(job_id))


@celery_app.task(name="graph.dispatch_outbox")  # type: ignore[untyped-decorator]
def dispatch_graph_outbox() -> int:
    from app.graph_dispatch import dispatch_pending_graph_jobs

    return runner.run(dispatch_pending_graph_jobs())


@celery_app.task(name="graph.reconcile_jobs")  # type: ignore[untyped-decorator]
def reconcile_graph_jobs() -> int:
    from app.graph_dispatch import reconcile_graph_jobs

    return runner.run(reconcile_graph_jobs())


@celery_app.task(name="graph.cleanup_projection")  # type: ignore[untyped-decorator]
def cleanup_graph_projection(cleanup_id: str) -> str:
    from app.graph_cleanup import execute_graph_cleanup

    return runner.run(execute_graph_cleanup(cleanup_id))


@celery_app.task(name="graph.dispatch_cleanup_outbox")  # type: ignore[untyped-decorator]
def dispatch_graph_cleanup_outbox() -> int:
    from app.graph_cleanup import dispatch_pending_graph_cleanup

    return runner.run(dispatch_pending_graph_cleanup())


@celery_app.task(name="graph.reconcile_cleanup_outbox")  # type: ignore[untyped-decorator]
def reconcile_graph_cleanup_outbox() -> int:
    from app.graph_cleanup import reconcile_graph_cleanup_outbox as reconcile

    return runner.run(reconcile())


async def _dispatch_pending(limit: int = 100) -> int:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db import engine
    from app.ingestion import sanitized_error
    from app.models import IndexingJob, IndexingOutbox, JobStatus

    sent = 0
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        rows = list(
            await db.scalars(
                select(IndexingOutbox)
                .join(IndexingJob, IndexingJob.id == IndexingOutbox.job_id)
                .where(
                    IndexingOutbox.dispatched_at.is_(None),
                    IndexingJob.status == JobStatus.QUEUED,
                )
                .order_by(IndexingOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.attempts += 1
            try:
                celery_app.send_task("ingestion.index_document", args=[row.job_id])
            except Exception as exc:
                row.last_error = sanitized_error(exc)
            else:
                row.dispatched_at = datetime.now(UTC)
                row.last_error = None
                sent += 1
        await db.commit()
    return sent


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
        return len(jobs)


@celery_app.task(name="ingestion.dispatch_outbox")  # type: ignore[untyped-decorator]
def dispatch_outbox() -> int:
    return runner.run(_dispatch_pending())


@celery_app.task(name="ingestion.reconcile_jobs")  # type: ignore[untyped-decorator]
def reconcile_indexing_jobs() -> int:
    return runner.run(_reconcile_indexing_jobs())
