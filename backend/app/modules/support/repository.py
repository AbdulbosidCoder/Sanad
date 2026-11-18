"""Database queries of the `support` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.support.models import SupportMessage, SupportTicket


async def get(db: AsyncSession, ticket_id: uuid.UUID, lock: bool = False) -> SupportTicket | None:
    stmt = select(SupportTicket).where(SupportTicket.id == ticket_id)
    if lock:
        stmt = stmt.with_for_update()
    return await db.scalar(stmt)


async def number_taken(db: AsyncSession, number: str) -> bool:
    return (
        await db.scalar(select(SupportTicket.id).where(SupportTicket.number == number)) is not None
    )


async def of_user(
    db: AsyncSession, user_id: uuid.UUID, offset: int, limit: int
) -> Sequence[SupportTicket]:
    return (
        await db.scalars(
            select(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.last_activity_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()


async def queue(
    db: AsyncSession,
    *,
    status: str | None,
    assignee_id: uuid.UUID | None,
    mine_or_free: uuid.UUID | None,
    unassigned: bool,
    offset: int,
    limit: int,
) -> Sequence[SupportTicket]:
    stmt = select(SupportTicket)
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    if assignee_id is not None:
        stmt = stmt.where(SupportTicket.assignee_id == assignee_id)
    if unassigned:
        stmt = stmt.where(SupportTicket.assignee_id.is_(None))
    if mine_or_free is not None:
        stmt = stmt.where(
            (SupportTicket.assignee_id == mine_or_free) | SupportTicket.assignee_id.is_(None)
        )
    order = (SupportTicket.last_activity_at.asc(),)  # who waits longest comes first
    return (await db.scalars(stmt.order_by(*order).offset(offset).limit(limit))).all()


async def messages(
    db: AsyncSession, ticket_id: uuid.UUID, with_internal: bool
) -> Sequence[SupportMessage]:
    stmt = select(SupportMessage).where(SupportMessage.ticket_id == ticket_id)
    if not with_internal:
        stmt = stmt.where(SupportMessage.internal.is_(False))
    return (await db.scalars(stmt.order_by(SupportMessage.created_at, SupportMessage.id))).all()
