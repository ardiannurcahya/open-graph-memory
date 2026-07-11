from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery("opengraphrag", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=270,
    task_time_limit=300,
    task_reject_on_worker_lost=True,
)


@celery_app.task(name="foundation.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"
