"""Database queries of the `notifications` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import EmailOutbox, Notification, NotificationPreference


async def preferences(db: AsyncSession, user_id: uuid.UUID) -> NotificationPreference | None:
    return await db.scalar(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )


async def inbox(
    db: AsyncSession, user_id: uuid.UUID, unread_only: bool, offset: int, limit: int
) -> Sequence[Notification]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
    return (await db.scalars(stmt.offset(offset).limit(limit))).all()


async def unread_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    n = await db.scalar(
        select(func.count()).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return int(n or 0)


async def mark_read(
    db: AsyncSession, user_id: uuid.UUID, now: datetime, notification_id: uuid.UUID | None
) -> int:
    stmt = update(Notification).where(
        Notification.user_id == user_id, Notification.read_at.is_(None)
    )
    if notification_id is not None:
        stmt = stmt.where(Notification.id == notification_id)
    result = await db.execute(stmt.values(read_at=now))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def pending_emails(db: AsyncSession, limit: int) -> Sequence[EmailOutbox]:
    return (
        await db.scalars(
            select(EmailOutbox)
            .where(EmailOutbox.status == "pending")
            .order_by(EmailOutbox.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()
