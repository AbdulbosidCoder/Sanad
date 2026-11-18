"""Database queries of the `cart` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cart.models import Cart, CartItem


async def find_cart(
    db: AsyncSession, user_id: uuid.UUID | None, token_hash: str | None
) -> Cart | None:
    if user_id is not None:
        return await db.scalar(select(Cart).where(Cart.user_id == user_id))
    if token_hash is not None:
        return await db.scalar(select(Cart).where(Cart.guest_token_hash == token_hash))
    return None


async def items_of(db: AsyncSession, cart_id: uuid.UUID) -> Sequence[CartItem]:
    return (
        await db.scalars(
            select(CartItem).where(CartItem.cart_id == cart_id).order_by(CartItem.created_at)
        )
    ).all()


async def get_item(db: AsyncSession, cart_id: uuid.UUID, variant_id: uuid.UUID) -> CartItem | None:
    return await db.get(CartItem, (cart_id, variant_id))


async def clear(db: AsyncSession, cart_id: uuid.UUID) -> None:
    await db.execute(delete(CartItem).where(CartItem.cart_id == cart_id))
