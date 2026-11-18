"""HTTP endpoints of the `analytics` module. Business logic lives in service.py."""

from typing import Literal

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.modules import module_router
from app.modules.analytics import service
from app.modules.analytics.schemas import ProductStat, SummaryOut
from app.modules.stores.service import StoreAccess, store_access

router = module_router("analytics")
_read = store_access("store.analytics_read")
Days = Query(30, ge=1, le=365)


@router.get("/seller/analytics/summary")
async def summary(
    days: int = Days,
    access: StoreAccess = Depends(_read),
    db: AsyncSession = Depends(get_session),
) -> SummaryOut:
    """Revenue, orders, views, conversion, rating, low stock and a by-day chart."""
    return await service.summary(db, access, days)


@router.get("/seller/analytics/products")
async def products(
    days: int = Days,
    sort: Literal["revenue", "units", "views", "conversion"] = "revenue",
    access: StoreAccess = Depends(_read),
    db: AsyncSession = Depends(get_session),
) -> list[ProductStat]:
    """Every product of the store: views, sold units, revenue, conversion, favourites."""
    return await service.products(db, access, days, sort)
