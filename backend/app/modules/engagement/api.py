"""HTTP endpoints of the `engagement` module. Business logic lives in service.py."""

import uuid

from fastapi import Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_optional_principal, get_principal
from app.core.db import get_session
from app.core.locale import Locale, request_locale
from app.core.modules import module_router
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, decode_cursor
from app.core.ratelimit import rate_limit
from app.modules.catalog.service import ProductCard
from app.modules.engagement import service
from app.modules.engagement.schemas import FavoriteState, ViewOut

router = module_router("engagement")


@router.get("/me/favorites")
async def favorites(
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    locale: Locale = Depends(request_locale),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> Page[ProductCard]:
    return await service.favorites(
        db, principal, locale, decode_cursor(cursor, "engagement"), limit
    )


@router.get("/me/favorites/flags")
async def flags(
    product_id: list[uuid.UUID] = Query(..., max_length=100),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> list[FavoriteState]:
    """Which of these products are in my favourites (hearts on a list of cards)."""
    return await service.favorite_flags(db, principal, product_id)


@router.put("/me/favorites/{product_id}")
async def add(
    product_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> FavoriteState:
    return await service.add_favorite(db, principal, product_id)


@router.delete("/me/favorites/{product_id}")
async def remove(
    product_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> FavoriteState:
    return await service.remove_favorite(db, principal, product_id)


@router.post(
    "/products/{product_id}/views",
    dependencies=[Depends(rate_limit("engagement.view", 120, 60, per="ip"))],
)
async def view(
    product_id: uuid.UUID,
    request: Request,
    x_device_id: str | None = Header(
        None, max_length=128, description="random id of a guest's device, kept by the client"
    ),
    principal: Principal | None = Depends(get_optional_principal),
    db: AsyncSession = Depends(get_session),
) -> ViewOut:
    """The product page was opened. Counted once per viewer per 30 minutes."""
    ip = request.client.host if request.client else None
    viewer = service.viewer_key(principal, x_device_id, ip)
    return await service.record_view(db, principal, product_id, viewer)


@router.get("/me/viewed")
async def viewed(
    locale: Locale = Depends(request_locale),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> list[ProductCard]:
    """Recently viewed products, newest first."""
    return await service.recently_viewed(db, principal, locale)
