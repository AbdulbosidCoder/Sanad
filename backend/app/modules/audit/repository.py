"""Database queries of the `audit` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog

CHAIN_LOCK = 774_211  # pg_advisory_xact_lock key: one writer of the chain at a time


async def lock_chain(db: AsyncSession) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": CHAIN_LOCK})


async def last_hash(db: AsyncSession) -> str | None:
    return await db.scalar(select(AuditLog.hash).order_by(AuditLog.seq.desc()).limit(1))


async def search(
    db: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action_prefixes: Sequence[str] | None,
    action: str | None,
    target_type: str | None,
    target_id: str | None,
    since: datetime | None,
    offset: int,
    limit: int,
) -> Sequence[AuditLog]:
    stmt = select(AuditLog)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if action_prefixes is not None:
        stmt = stmt.where(or_(*(AuditLog.action.startswith(p) for p in action_prefixes)))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if target_type:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if target_id:
        stmt = stmt.where(AuditLog.target_id == target_id)
    if since is not None:
        stmt = stmt.where(AuditLog.created_at >= since)
    stmt = stmt.order_by(AuditLog.seq.desc()).offset(offset).limit(limit)
    return (await db.scalars(stmt)).all()


async def chain(db: AsyncSession, after_seq: int, limit: int) -> Sequence[AuditLog]:
    return (
        await db.scalars(
            select(AuditLog).where(AuditLog.seq > after_seq).order_by(AuditLog.seq).limit(limit)
        )
    ).all()
