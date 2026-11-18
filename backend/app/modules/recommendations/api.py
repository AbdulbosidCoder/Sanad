"""HTTP endpoints of the `recommendations` module. Business logic lives in service.py."""

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_optional_principal
from app.core.db import get_session
from app.core.locale import Locale, request_locale
from app.core.modules import module_router
from app.modules.recommendations import service
from app.modules.recommendations.schemas import Block, HomeOut

router = module_router("recommendations")


@router.get("/home")
async def home(
    locale: Locale = Depends(request_locale),
    principal: Principal | None = Depends(get_optional_principal),
    db: AsyncSession = Depends(get_session),
) -> HomeOut:
    """Home page: categories, brands and product blocks (for you, new, sale, trending, hits)."""
    return await service.home(db, principal, locale)


@router.get("/products/{product_id}/recommendations")
async def for_product(
    product_id: uuid.UUID,
    locale: Locale = Depends(request_locale),
    db: AsyncSession = Depends(get_session),
) -> list[Block]:
    return await service.for_product(db, product_id, locale)
