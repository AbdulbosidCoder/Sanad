"""HTTP endpoints of the `search` module. Business logic lives in service.py."""

from decimal import Decimal

from fastapi import Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_optional_principal, get_principal, require_permission
from app.core.db import get_session
from app.core.locale import Locale, request_locale
from app.core.modules import module_router
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, decode_cursor
from app.core.ratelimit import rate_limit
from app.modules.catalog.service import ProductCard, Sort
from app.modules.search import service
from app.modules.search.schemas import HistoryItem, PopularQuery, SuggestOut

router = module_router("search")


@router.get("/search", dependencies=[Depends(rate_limit("search", 60, 60))])
async def search(
    q: str = Query(..., min_length=1, max_length=100),
    category: str | None = None,
    brand: list[str] = Query(default_factory=list),
    size: list[str] = Query(default_factory=list),
    price_min: Decimal | None = Query(None, ge=0),
    price_max: Decimal | None = Query(None, ge=0),
    in_stock: bool | None = None,
    sort: Sort = "relevance",
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    locale: Locale = Depends(request_locale),
    principal: Principal | None = Depends(get_optional_principal),
    db: AsyncSession = Depends(get_session),
) -> Page[ProductCard]:
    """Full-text search in all languages, typo tolerant; remembered in the buyer's history."""
    return await service.search(
        db,
        principal,
        q=q,
        locale=locale,
        category=category,
        brands=brand,
        sizes=size,
        price_min=price_min,
        price_max=price_max,
        in_stock=in_stock,
        sort=sort,
        offset=decode_cursor(cursor, "search"),
        limit=limit,
    )


@router.get("/search/suggest", dependencies=[Depends(rate_limit("search.suggest", 120, 60))])
async def suggest(
    q: str = Query(..., max_length=100),
    locale: Locale = Depends(request_locale),
    principal: Principal | None = Depends(get_optional_principal),
    db: AsyncSession = Depends(get_session),
) -> SuggestOut:
    return await service.suggest(db, principal, q, locale)


@router.get("/search/popular")
async def popular(db: AsyncSession = Depends(get_session)) -> list[PopularQuery]:
    """Top queries of the last 7 days (for the empty search screen)."""
    return await service.popular_queries(db)


@router.get("/me/search-history")
async def history(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> list[HistoryItem]:
    return await service.my_history(db, principal)


@router.delete("/me/search-history", status_code=204)
async def clear(
    q: str | None = Query(None, description="one query; without it the whole history"),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await service.clear_history(db, principal, q)
    return Response(status_code=204)


@router.post("/admin/search/reindex")
async def reindex(
    _: Principal = Depends(require_permission("ops.jobs_retry")),
    db: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    return {"products": await service.reindex_all(db)}
