"""Database queries of the `inventory` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.inventory.models import Inventory, StockMovement


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
