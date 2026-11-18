"""Celery application: background jobs (translations, indexing, notifications...)."""

from celery import Celery

from app.core.config import get_settings

celery_app = Celery("sanad", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    beat_schedule={
        "orders-expire-unpaid": {"task": "orders.expire_unpaid", "schedule": 300.0},
        "i18n-translate-pending": {"task": "i18n.translate_pending", "schedule": 60.0},
        "notifications-send-emails": {"task": "notifications.send_emails", "schedule": 60.0},
    },
)


@celery_app.task(name="system.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    """Smoke-test task: `celery -A app.workers.celery_app call system.ping`."""
    return "pong"


@celery_app.task(name="orders.expire_unpaid")  # type: ignore[untyped-decorator]
def expire_unpaid_orders() -> int:
    """Cancels unpaid orders whose stock hold ran out (every 5 minutes)."""
    import asyncio

    from app.modules import setup_all
    from app.modules.orders.service import expire_unpaid

    setup_all()  # payment/order event handlers live in module setup hooks
    return asyncio.run(expire_unpaid())


@celery_app.task(name="i18n.translate_pending")  # type: ignore[untyped-decorator]
def translate_pending() -> int:
    """Machine-translates queued product texts (every minute)."""
    import asyncio

    from app.modules import setup_all
    from app.modules.i18n.service import translate_pending_job

    setup_all()
    return asyncio.run(translate_pending_job())


@celery_app.task(name="notifications.send_emails")  # type: ignore[untyped-decorator]
def send_emails() -> int:
    """Sends queued e-mails (every minute)."""
    import asyncio

    from app.modules import setup_all
    from app.modules.notifications.service import send_emails_job

    setup_all()
    return asyncio.run(send_emails_job())
