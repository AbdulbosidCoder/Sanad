"""HTTP endpoints of the `cart` module. Business logic lives in service.py.

Guests send ``X-Cart-Token`` (a random string of 32+ characters the client generates and
keeps); signed-in users need no token.
"""

import uuid

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_optional_principal, get_principal
from app.core.db import get_session
from app.core.errors import AppError
from app.core.modules import module_router
from app.modules.cart import service
from app.modules.cart.schemas import AddItemIn, CartOut, SetQuantityIn
from app.modules.cart.service import CartOwner

router = module_router("cart")

TokenHeader = Header(None, alias="X-Cart-Token", max_length=128, description="guest cart token")


async def cart_owner(
    principal: Principal | None = Depends(get_optional_principal),
    x_cart_token: str | None = TokenHeader,
) -> CartOwner:
    return service.owner(principal.user_id if principal else None, x_cart_token)


@router.get("/cart")
async def get_cart(
    who: CartOwner = Depends(cart_owner), db: AsyncSession = Depends(get_session)
) -> CartOut:
    """Cart grouped by seller, with today's prices and stock problems."""
    return await service.get_cart(db, who)


@router.post("/cart/items")
async def add_item(
    data: AddItemIn, who: CartOwner = Depends(cart_owner), db: AsyncSession = Depends(get_session)
) -> CartOut:
    """Adds an item; if it is already in the cart, the quantities add up."""
    return await service.add_item(db, who, data.variant_id, data.quantity)


@router.patch("/cart/items/{variant_id}")
async def set_quantity(
    variant_id: uuid.UUID,
    data: SetQuantityIn,
    who: CartOwner = Depends(cart_owner),
    db: AsyncSession = Depends(get_session),
) -> CartOut:
    return await service.set_quantity(db, who, variant_id, data.quantity)


@router.delete("/cart/items/{variant_id}")
async def remove_item(
    variant_id: uuid.UUID,
    who: CartOwner = Depends(cart_owner),
    db: AsyncSession = Depends(get_session),
) -> CartOut:
    return await service.remove_item(db, who, variant_id)


@router.delete("/cart", status_code=204)
async def clear_cart(
    who: CartOwner = Depends(cart_owner), db: AsyncSession = Depends(get_session)
) -> None:
    await service.clear_cart(db, who)


@router.post("/cart/merge")
async def merge(
    x_cart_token: str | None = TokenHeader,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> CartOut:
    """Call right after sign-in with the guest token: the guest cart joins the user's."""
    if not x_cart_token:
        raise AppError("cart", "CART_TOKEN_REQUIRED", "Send X-Cart-Token", status=400)
    return await service.merge(db, principal.user_id, x_cart_token)
