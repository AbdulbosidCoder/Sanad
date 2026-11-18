"""HTTP endpoints of the `i18n` module. Business logic lives in service.py."""

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.modules import module_router
from app.modules.i18n import service
from app.modules.i18n.schemas import Locale, TranslationIn, TranslationOut
from app.modules.stores.service import StoreAccess, store_access

router = module_router("i18n")


@router.get("/seller/products/{product_id}/translations")
async def translations(
    product_id: uuid.UUID,
    access: StoreAccess = Depends(store_access()),
    db: AsyncSession = Depends(get_session),
) -> list[TranslationOut]:
    """The product in uz / ru / en: original, machine, manual, pending or missing."""
    return await service.product_translations(db, access, product_id)


@router.put("/seller/products/{product_id}/translations/{locale}")
async def edit(
    product_id: uuid.UUID,
    locale: Locale,
    data: TranslationIn,
    access: StoreAccess = Depends(store_access("products.write")),
    db: AsyncSession = Depends(get_session),
) -> list[TranslationOut]:
    """Seller's own translation; the machine never overwrites it."""
    return await service.edit_translation(db, access, product_id, locale, data)


@router.post("/seller/products/{product_id}/translations/{locale}/retranslate")
async def retranslate(
    product_id: uuid.UUID,
    locale: Locale,
    access: StoreAccess = Depends(store_access("products.write")),
    db: AsyncSession = Depends(get_session),
) -> list[TranslationOut]:
    return await service.retranslate(db, access, product_id, locale)
