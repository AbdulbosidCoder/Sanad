"""Database queries of the `payments` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import uuid7
from app.modules.payments.models import LedgerEntry, Payment, Refund, WebhookEvent


async def lock_payment(db: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
    return await db.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())


async def lock_by_provider_id(db: AsyncSession, provider: str, pid: str) -> Payment | None:
    return await db.scalar(
        select(Payment)
        .where(Payment.provider == provider, Payment.provider_payment_id == pid)
        .with_for_update()
    )


async def payments_of_order(db: AsyncSession, order_id: uuid.UUID) -> Sequence[Payment]:
    return (
        await db.scalars(
            select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at)
        )
    ).all()


async def remember_webhook(
    db: AsyncSession, provider: str, event_id: str, payload: dict[str, object]
) -> bool:
    """False if this event was already received."""
    stmt = (
        insert(WebhookEvent)
        .values(id=uuid7(), provider=provider, event_id=event_id, payload=payload)
        .on_conflict_do_nothing()
        .returning(WebhookEvent.id)
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def list_payments(
    db: AsyncSession, status: str | None, offset: int, limit: int
) -> Sequence[Payment]:
    stmt = select(Payment).order_by(Payment.created_at.desc(), Payment.id.desc())
    if status:
        stmt = stmt.where(Payment.status == status)
    return (await db.scalars(stmt.offset(offset).limit(limit))).all()


async def get_refund(db: AsyncSession, refund_id: uuid.UUID, lock: bool = False) -> Refund | None:
    stmt = select(Refund).where(Refund.id == refund_id)
    if lock:
        stmt = stmt.with_for_update()
    found: Refund | None = await db.scalar(stmt)
    return found


async def refunds_of_payment(db: AsyncSession, payment_id: uuid.UUID) -> Sequence[Refund]:
    return (await db.scalars(select(Refund).where(Refund.payment_id == payment_id))).all()


async def list_refunds(
    db: AsyncSession, status: str | None, offset: int, limit: int
) -> Sequence[Refund]:
    stmt = select(Refund).order_by(Refund.created_at.desc(), Refund.id.desc())
    if status:
        stmt = stmt.where(Refund.status == status)
    return (await db.scalars(stmt.offset(offset).limit(limit))).all()


async def ledger(
    db: AsyncSession, store_id: uuid.UUID | None, offset: int, limit: int
) -> Sequence[LedgerEntry]:
    stmt = select(LedgerEntry).order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
    if store_id:
        stmt = stmt.where(LedgerEntry.store_id == store_id)
    return (await db.scalars(stmt.offset(offset).limit(limit))).all()


async def ledger_of_store(db: AsyncSession, store_id: uuid.UUID) -> Sequence[LedgerEntry]:
    return (await db.scalars(select(LedgerEntry).where(LedgerEntry.store_id == store_id))).all()
