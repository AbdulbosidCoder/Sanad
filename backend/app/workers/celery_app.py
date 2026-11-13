"""Celery application: background jobs (translations, indexing, notifications...)."""

from celery import Celery

from app.core.config import get_settings

celery_app = Celery("sanad", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    beat_schedule={},
)


@celery_app.task(name="system.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    """Smoke-test task: `celery -A app.workers.celery_app call system.ping`."""
    return "pong"
