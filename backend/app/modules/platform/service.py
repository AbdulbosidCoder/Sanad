"""Business logic of the `platform` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

Ops dashboard for the developer role: background queues and their failures, without
any personal data (only counts).
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import AppError
from app.core.redis import get_redis
from app.modules.audit import service as audit
from app.modules.i18n import service as i18n
from app.modules.notifications import service as notifications
from app.modules.platform.schemas import OpsOut, Queue, RetryOut


async def overview(db: AsyncSession) -> OpsOut:
    try:
        await db.execute(text("SELECT 1"))
        database = True
    except Exception:
        database = False
    try:
        redis = bool(await get_redis().ping())
    except Exception:
        redis = False
    return OpsOut(
        queues=[
            Queue(name="translations", counts=await i18n.job_counts(db), schedule="every 60 s"),
            Queue(
                name="emails", counts=await notifications.outbox_counts(db), schedule="every 60 s"
            ),
        ],
        database=database,
        redis=redis,
    )


async def retry(db: AsyncSession, actor: Principal, queue: str) -> RetryOut:
    """Failed jobs of a queue go back to pending (attempts reset)."""
    if queue == "translations":
        count = await i18n.retry_failed_jobs(db)
    elif queue == "emails":
        count = await notifications.retry_failed_emails(db)
    else:
        raise AppError("platform", "UNKNOWN_QUEUE", f"Unknown queue: {queue}", status=404)
    await audit.record(db, actor.user_id, "ops.retry", "queue", queue, {"retried": count})
    await db.commit()
    return RetryOut(queue=queue, retried=count)
