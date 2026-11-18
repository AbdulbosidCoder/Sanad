"""Database queries of the `inventory` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import Inventory, StockMovement, StockReservation


async def stock_of_store(db: AsyncSession, store_id: uuid.UUID) -> dict[uuid.UUID, Inventory]:
    rows = await db.scalars(select(Inventory).where(Inventory.store_id == store_id))
    return {r.variant_id: r for r in rows}


async def lock_stock(db: AsyncSession, variant_id: uuid.UUID) -> Inventory | None:
    return await db.scalar(
        select(Inventory).where(Inventory.variant_id == variant_id).with_for_update()
    )


async def movements(db: AsyncSession, variant_id: uuid.UUID, limit: int) -> Sequence[StockMovement]:
    return (
        await db.scalars(
            select(StockMovement)
            .where(StockMovement.variant_id == variant_id)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
            .limit(limit)
        )
    ).all()


async def try_reserve(db: AsyncSession, variant_id: uuid.UUID, quantity: int) -> Inventory | None:
    """Atomic: holds ``quantity`` only if that much is free. None = not enough stock."""
    found: Inventory | None = await db.scalar(
        update(Inventory)
        .where(
            Inventory.variant_id == variant_id,
            Inventory.on_hand - Inventory.reserved >= quantity,
        )
        .values(reserved=Inventory.reserved + quantity, version=Inventory.version + 1)
        .returning(Inventory)
        .execution_options(populate_existing=True)
    )
    return found


async def reservations_of(
    db: AsyncSession, order_id: uuid.UUID, status: str = "active"
) -> Sequence[StockReservation]:
    return (
        await db.scalars(
            select(StockReservation)
            .where(StockReservation.order_id == order_id, StockReservation.status == status)
            .with_for_update()
        )
    ).all()


async def expired_order_ids(db: AsyncSession, now: datetime, limit: int) -> list[uuid.UUID]:
    rows = await db.scalars(
        select(StockReservation.order_id)
        .where(StockReservation.status == "active", StockReservation.expires_at <= now)
        .distinct()
        .limit(limit)
    )
    return list(rows.all())


async def stock_by_variants(
    db: AsyncSession, variant_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Inventory]:
    if not variant_ids:
        return {}
    rows = await db.scalars(select(Inventory).where(Inventory.variant_id.in_(variant_ids)))
    return {r.variant_id: r for r in rows}
