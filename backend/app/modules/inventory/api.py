"""HTTP endpoints of the `inventory` module. Business logic lives in service.py."""

import uuid

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.modules import module_router
from app.modules.inventory import service
from app.modules.inventory.schemas import MovementOut, StockOut, StockUpdate
from app.modules.stores.service import StoreAccess, store_access

router = module_router("inventory")


@router.get("/seller/inventory")
async def list_stock(
    low_stock: bool = Query(False, description="only variants at or below their threshold"),
    access: StoreAccess = Depends(store_access()),
    db: AsyncSession = Depends(get_session),
) -> list[StockOut]:
    """Stock of every variant of the store."""
    return await service.list_stock(db, access, low_stock)


@router.patch("/seller/inventory/{variant_id}")
async def update_stock(
    variant_id: uuid.UUID,
    data: StockUpdate,
    access: StoreAccess = Depends(store_access("inventory.write")),
    db: AsyncSession = Depends(get_session),
) -> StockOut:
    return await service.update_stock(db, access, variant_id, data)


@router.get("/seller/inventory/{variant_id}/movements")
async def movements(
    variant_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    access: StoreAccess = Depends(store_access()),
    db: AsyncSession = Depends(get_session),
) -> list[MovementOut]:
    """History of stock changes of a variant, newest first."""
    return await service.list_movements(db, access, variant_id, limit)
