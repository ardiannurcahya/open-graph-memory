from datetime import UTC, datetime

from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded

from app.async_runner import runner
from app.config import get_settings

settings = get_settings()
celery_app = Celery("opengraphrag", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=270,
    task_time_limit=300,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "dispatch-indexing-outbox": {
            "task": "ingestion.dispatch_outbox",
            "schedule": settings.outbox_poll_seconds,
        }
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


@celery_app.task(name="ingestion.dispatch_outbox")  # type: ignore[untyped-decorator]
def dispatch_outbox() -> int:
    return runner.run(_dispatch_pending())
