"""HTTP endpoints of the `orders` module. Business logic lives in service.py."""

import uuid
from typing import Literal

from fastapi import Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_permission, require_sensitive_action
from app.core.db import get_session
from app.core.modules import module_router
from app.modules.orders import service
from app.modules.orders.schemas import (
    CancelIn,
    CheckoutIn,
    CheckoutOut,
    OrderOut,
    OrderSummary,
    PreviewOut,
    ReturnDecisionIn,
    ReturnIn,
    ReturnOut,
    SellerOrderDetail,
    StatusIn,
)
from app.modules.stores.service import StoreAccess, store_access

router = module_router("orders")

Offset = Query(0, ge=0)
Limit = Query(20, ge=1, le=100)
SellerStatusFilter = Literal["new", "confirmed", "shipped", "delivered", "cancelled", "returned"]


@router.post("/checkout/preview")
async def preview(
    data: CheckoutIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> PreviewOut:
    """Totals per seller and the delivery address, before placing the order."""
    return await service.preview(db, principal, data)


@router.post("/checkout", status_code=201)
async def checkout(
    data: CheckoutIn,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=8,
        max_length=64,
        description="random per checkout attempt; a retry with the same key returns the same order",
    ),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> CheckoutOut:
    return await service.checkout(db, principal, data, idempotency_key)


@router.get("/orders")
async def list_orders(
    offset: int = Offset,
    limit: int = Limit,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> list[OrderSummary]:
    return await service.list_orders(db, principal, offset, limit)


@router.get("/orders/returns")
async def my_returns(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> list[ReturnOut]:
    return await service.my_returns(db, principal)


@router.get("/orders/{order_id}")
async def get_order(
    order_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> OrderOut:
    """Order with every seller's part, items, status history and payments (tracking)."""
    return await service.get_order(db, principal, order_id)


@router.post("/orders/{order_id}/cancel")
async def cancel(
    order_id: uuid.UUID,
    data: CancelIn | None = None,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> OrderOut:
    """Before anything ships. A paid order is refunded automatically."""
    return await service.cancel_order(db, principal, order_id, data.reason if data else "")


@router.post("/orders/{order_id}/items/{item_id}/return", status_code=201)
async def request_return(
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ReturnIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> ReturnOut:
    """Within 14 days after delivery."""
    return await service.request_return(db, principal, order_id, item_id, data)


# ---------------------------------------------------------------- seller


@router.get("/seller/orders")
async def store_orders(
    status: SellerStatusFilter | None = None,
    offset: int = Offset,
    limit: int = Limit,
    access: StoreAccess = Depends(store_access()),
    db: AsyncSession = Depends(get_session),
) -> list[SellerOrderDetail]:
    return await service.store_orders(db, access, status, offset, limit)


@router.get("/seller/orders/{seller_order_id}")
async def store_order(
    seller_order_id: uuid.UUID,
    access: StoreAccess = Depends(store_access()),
    db: AsyncSession = Depends(get_session),
) -> SellerOrderDetail:
    return await service.store_order(db, access, seller_order_id)


@router.patch("/seller/orders/{seller_order_id}/status")
async def set_status(
    seller_order_id: uuid.UUID,
    data: StatusIn,
    access: StoreAccess = Depends(store_access("orders.seller_manage")),
    db: AsyncSession = Depends(get_session),
) -> SellerOrderDetail:
    """new → confirmed → shipped (tracking number) → delivered; or cancelled before shipping."""
    return await service.seller_set_status(db, access, seller_order_id, data)


@router.get("/seller/returns")
async def store_returns(
    status: Literal["requested", "approved", "rejected", "received", "refunded"] | None = None,
    access: StoreAccess = Depends(store_access()),
    db: AsyncSession = Depends(get_session),
) -> list[ReturnOut]:
    return await service.store_returns(db, access, status)


@router.patch("/seller/returns/{return_id}")
async def decide_return(
    return_id: uuid.UUID,
    data: ReturnDecisionIn,
    access: StoreAccess = Depends(store_access("returns.decide")),
    db: AsyncSession = Depends(get_session),
) -> ReturnOut:
    """approve / reject; receive = the item came back: stock restored, refund goes to finance."""
    return await service.decide_return(db, access, return_id, data)


# ---------------------------------------------------------------- platform staff


@router.get("/admin/orders")
async def admin_orders(
    status: Literal["placed", "partially_fulfilled", "completed", "cancelled"] | None = None,
    offset: int = Offset,
    limit: int = Limit,
    _: Principal = Depends(require_permission("orders.read")),
    db: AsyncSession = Depends(get_session),
) -> list[OrderSummary]:
    return await service.admin_orders(db, status, offset, limit)


@router.post("/admin/seller-orders/{seller_order_id}/status")
async def override_status(
    seller_order_id: uuid.UUID,
    data: StatusIn,
    principal: Principal = Depends(require_sensitive_action("orders.status_override")),
    db: AsyncSession = Depends(get_session),
) -> SellerOrderDetail:
    return await service.staff_set_status(db, principal, seller_order_id, data)
