"""Database queries of the `orders` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    ReturnRequest,
    SellerOrder,
)


async def find_by_key(db: AsyncSession, user_id: uuid.UUID, key: str) -> Order | None:
    return await db.scalar(
        select(Order).where(Order.user_id == user_id, Order.idempotency_key == key)
    )


async def number_taken(db: AsyncSession, number: str) -> bool:
    return bool(await db.scalar(select(func.count()).where(Order.number == number)))


async def get_order(db: AsyncSession, order_id: uuid.UUID, lock: bool = False) -> Order | None:
    stmt = select(Order).where(Order.id == order_id)
    if lock:
        stmt = stmt.with_for_update()
    found: Order | None = await db.scalar(stmt)
    return found


async def orders_of(
    db: AsyncSession,
    user_id: uuid.UUID | None,
    offset: int,
    limit: int,
    status: str | None = None,
) -> Sequence[Order]:
    stmt = select(Order).order_by(Order.created_at.desc(), Order.id.desc())
    if user_id is not None:
        stmt = stmt.where(Order.user_id == user_id)
    if status:
        stmt = stmt.where(Order.status == status)
    return (await db.scalars(stmt.offset(offset).limit(limit))).all()


async def seller_orders_of(db: AsyncSession, order_id: uuid.UUID) -> Sequence[SellerOrder]:
    return (
        await db.scalars(
            select(SellerOrder).where(SellerOrder.order_id == order_id).order_by(SellerOrder.number)
        )
    ).all()


async def get_seller_order(
    db: AsyncSession, seller_order_id: uuid.UUID, lock: bool = False
) -> SellerOrder | None:
    stmt = select(SellerOrder).where(SellerOrder.id == seller_order_id)
    if lock:
        stmt = stmt.with_for_update()
    found: SellerOrder | None = await db.scalar(stmt)
    return found


async def store_orders(
    db: AsyncSession, store_id: uuid.UUID, status: str | None, offset: int, limit: int
) -> Sequence[SellerOrder]:
    stmt = (
        select(SellerOrder)
        .where(SellerOrder.store_id == store_id)
        .order_by(SellerOrder.created_at.desc(), SellerOrder.id.desc())
    )
    if status:
        stmt = stmt.where(SellerOrder.status == status)
    return (await db.scalars(stmt.offset(offset).limit(limit))).all()


async def items_of(db: AsyncSession, seller_order_ids: Sequence[uuid.UUID]) -> Sequence[OrderItem]:
    if not seller_order_ids:
        return []
    return (
        await db.scalars(
            select(OrderItem)
            .where(OrderItem.seller_order_id.in_(seller_order_ids))
            .order_by(OrderItem.title, OrderItem.sku)
        )
    ).all()


async def history_of(
    db: AsyncSession, seller_order_ids: Sequence[uuid.UUID]
) -> Sequence[OrderStatusHistory]:
    if not seller_order_ids:
        return []
    return (
        await db.scalars(
            select(OrderStatusHistory)
            .where(OrderStatusHistory.seller_order_id.in_(seller_order_ids))
            .order_by(OrderStatusHistory.created_at, OrderStatusHistory.id)
        )
    ).all()


async def get_item(db: AsyncSession, item_id: uuid.UUID) -> OrderItem | None:
    return await db.get(OrderItem, item_id)


async def returns_of_item(db: AsyncSession, item_id: uuid.UUID) -> Sequence[ReturnRequest]:
    return (
        await db.scalars(select(ReturnRequest).where(ReturnRequest.order_item_id == item_id))
    ).all()


async def get_return(db: AsyncSession, return_id: uuid.UUID) -> ReturnRequest | None:
    return await db.scalar(
        select(ReturnRequest).where(ReturnRequest.id == return_id).with_for_update()
    )


async def return_by_refund(db: AsyncSession, refund_id: uuid.UUID) -> ReturnRequest | None:
    return await db.scalar(select(ReturnRequest).where(ReturnRequest.refund_id == refund_id))


async def store_returns(
    db: AsyncSession, store_id: uuid.UUID, status: str | None
) -> Sequence[ReturnRequest]:
    stmt = (
        select(ReturnRequest)
        .join(SellerOrder, SellerOrder.id == ReturnRequest.seller_order_id)
        .where(SellerOrder.store_id == store_id)
        .order_by(ReturnRequest.created_at.desc())
    )
    if status:
        stmt = stmt.where(ReturnRequest.status == status)
    return (await db.scalars(stmt)).all()


async def returns_of_user(db: AsyncSession, user_id: uuid.UUID) -> Sequence[ReturnRequest]:
    return (
        await db.scalars(
            select(ReturnRequest)
            .where(ReturnRequest.user_id == user_id)
            .order_by(ReturnRequest.created_at.desc())
        )
    ).all()


async def purchased(
    db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID
) -> uuid.UUID | None:
    """An order item of a delivered seller order of this user for the product."""
    found: uuid.UUID | None = await db.scalar(
        select(OrderItem.id)
        .join(SellerOrder, SellerOrder.id == OrderItem.seller_order_id)
        .join(Order, Order.id == SellerOrder.order_id)
        .where(
            Order.user_id == user_id,
            OrderItem.product_id == product_id,
            SellerOrder.status.in_(("delivered", "returned")),
        )
        .limit(1)
    )
    return found
