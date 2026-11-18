"""Business logic of the `orders` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

Checkout in one transaction: cart lines -> order + one seller order per store -> stock
held (``inventory.reserve``) -> payment opened -> cart emptied. Any failure rolls all of
it back. The payment outcome arrives as an event:
- ``PaymentSucceeded``: order paid, held stock leaves the shelf;
- ``PaymentFailed``: stock released, order cancelled, items go back to the cart.
Unpaid orders whose stock hold expired are cancelled by a background job.
"""

import logging
import secrets
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import AppError
from app.core.events import publish, subscribe
from app.core.models import uuid7
from app.modules.cart import service as cart
from app.modules.identity import service as identity
from app.modules.inventory import service as inventory
from app.modules.inventory.service import ReserveLine
from app.modules.orders import repository as repo
from app.modules.orders.events import (
    OrderCancelled,
    OrderPaid,
    OrderPlaced,
    SellerOrderStatusChanged,
)
from app.modules.orders.models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    ReturnRequest,
    SellerOrder,
)
from app.modules.orders.schemas import (
    CheckoutIn,
    CheckoutOut,
    HistoryOut,
    ItemOut,
    OrderOut,
    OrderSummary,
    PreviewGroup,
    PreviewOut,
    ReturnDecisionIn,
    ReturnIn,
    ReturnOut,
    SellerOrderDetail,
    SellerOrderOut,
    StatusIn,
)
from app.modules.payments import service as payments
from app.modules.payments.events import PaymentFailed, PaymentSucceeded, RefundCompleted
from app.modules.payments.service import Split
from app.modules.stores import service as stores
from app.modules.stores.service import StoreAccess

MODULE = "orders"
CENT = Decimal("0.01")
RETURN_DAYS = 14

# Seller order status machine: from -> allowed next statuses.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "new": ("confirmed", "cancelled"),
    "confirmed": ("shipped", "cancelled"),
    "shipped": ("delivered",),
    "delivered": (),
    "cancelled": (),
    "returned": (),
}

logger = logging.getLogger("app.modules.orders")


def _error(code: str, detail: str, status: int) -> AppError:
    return AppError(MODULE, code, detail, status=status)


def _log(msg: str, **fields: object) -> None:
    logger.info(msg, extra={"extra_fields": {k: str(v) for k, v in fields.items()}})


def _now() -> datetime:
    return datetime.now(UTC)


def _not_found() -> AppError:
    return _error("ORDER_NOT_FOUND", "Order not found", 404)


# ---------------------------------------------------------------- wiring


def setup() -> None:
    subscribe(PaymentSucceeded, on_payment_succeeded)
    subscribe(PaymentFailed, on_payment_failed)
    subscribe(RefundCompleted, on_refund_completed)


# ---------------------------------------------------------------- responses


async def _seller_parts(
    db: AsyncSession, parts: list[SellerOrder], with_history: bool = True
) -> list[SellerOrderOut]:
    ids = [s.id for s in parts]
    items: dict[uuid.UUID, list[ItemOut]] = defaultdict(list)
    for i in await repo.items_of(db, ids):
        items[i.seller_order_id].append(ItemOut.model_validate(i))
    history: dict[uuid.UUID, list[HistoryOut]] = defaultdict(list)
    if with_history:
        for h in await repo.history_of(db, ids):
            history[h.seller_order_id].append(HistoryOut.model_validate(h))
    out = []
    for s in parts:
        brief = await stores.get_store_brief(db, s.store_id)
        part = SellerOrderOut.model_validate(s)
        part.store_name = brief.name if brief else ""
        part.items = items[s.id]
        part.history = history[s.id]
        out.append(part)
    return out


async def _order_out(db: AsyncSession, order: Order) -> OrderOut:
    out = OrderOut.model_validate(order)
    out.seller_orders = await _seller_parts(db, list(await repo.seller_orders_of(db, order.id)))
    out.payments = await payments.payments_of_order(db, order.id)
    return out


# ---------------------------------------------------------------- checkout


def _group(lines: list[cart.CheckoutLine]) -> dict[uuid.UUID, list[cart.CheckoutLine]]:
    groups: dict[uuid.UUID, list[cart.CheckoutLine]] = defaultdict(list)
    for line in lines:
        groups[line.item.store_id].append(line)
    return groups


async def preview(db: AsyncSession, principal: Principal, data: CheckoutIn) -> PreviewOut:
    lines = await cart.checkout_lines(db, principal.user_id)
    groups = []
    for store_id, part in _group(lines).items():
        brief = await stores.get_store_brief(db, store_id)
        groups.append(
            PreviewGroup(
                store_id=store_id,
                store_name=brief.name if brief else "",
                item_count=sum(x.quantity for x in part),
                subtotal=sum((x.item.price * x.quantity for x in part), Decimal(0)),
            )
        )
    return PreviewOut(
        groups=groups,
        total=sum((g.subtotal for g in groups), Decimal(0)),
        shipping_address=await identity.address_snapshot(db, principal.user_id, data.address_id),
        payment_methods=payments.available_providers(),
    )


async def _new_number(db: AsyncSession) -> str:
    while True:
        number = f"SN-{_now():%y%m%d}-{secrets.randbelow(10**6):06d}"
        if not await repo.number_taken(db, number):
            return number


async def checkout(
    db: AsyncSession, principal: Principal, data: CheckoutIn, idempotency_key: str
) -> CheckoutOut:
    """Places the order. The same Idempotency-Key returns the same order (safe to retry)."""
    existing = await repo.find_by_key(db, principal.user_id, idempotency_key)
    if existing is not None:
        return await _checkout_out(db, existing)

    address = await identity.address_snapshot(db, principal.user_id, data.address_id)
    if address is None:
        raise _error("ADDRESS_REQUIRED", "Add a delivery address first", 409)
    lines = await cart.checkout_lines(db, principal.user_id)
    groups = _group(lines)

    order = Order(
        id=uuid7(),
        number=await _new_number(db),
        user_id=principal.user_id,
        shipping_address=address,
        total=sum((x.item.price * x.quantity for x in lines), Decimal(0)),
        currency="UZS",
        status="placed",
        payment_status="pending",
        payment_provider=data.payment_method,
        idempotency_key=idempotency_key,
    )
    db.add(order)
    await db.flush()

    splits: list[Split] = []
    reserve: list[ReserveLine] = []
    for n, (store_id, part) in enumerate(groups.items(), start=1):
        subtotal = sum((x.item.price * x.quantity for x in part), Decimal(0))
        rate = await stores.commission_rate(db, store_id)
        seller_order = SellerOrder(
            id=uuid7(),
            order_id=order.id,
            store_id=store_id,
            number=f"{order.number}-{n}",
            subtotal=subtotal,
            commission=(subtotal * rate).quantize(CENT, rounding=ROUND_HALF_UP),
            status="new",
        )
        db.add(seller_order)
        await db.flush()  # no ORM relationships: insert parents before children
        db.add(
            OrderStatusHistory(
                id=uuid7(),
                seller_order_id=seller_order.id,
                from_status=None,
                to_status="new",
                actor_id=principal.user_id,
            )
        )
        for x in part:
            db.add(
                OrderItem(
                    id=uuid7(),
                    seller_order_id=seller_order.id,
                    variant_id=x.item.variant_id,
                    product_id=x.item.product_id,
                    title=x.item.product_title,
                    sku=x.item.sku,
                    attributes=x.item.attributes,
                    cover_url=x.item.cover_url,
                    unit_price=x.item.price,
                    quantity=x.quantity,
                    line_total=x.item.price * x.quantity,
                )
            )
            reserve.append(ReserveLine(x.item.variant_id, store_id, x.quantity))
        splits.append(Split(store_id, seller_order.id, subtotal, seller_order.commission))

    try:
        await db.flush()
        await inventory.reserve(db, order.id, reserve, get_settings().reservation_ttl_minutes)
        payment = await payments.create_payment(
            db,
            order_id=order.id,
            user_id=principal.user_id,
            amount=order.total,
            currency=order.currency,
            splits=splits,
            provider_code=data.payment_method,
            description=f"Order {order.number}",
        )
        await cart.clear_user_cart(db, principal.user_id)
        await publish(db, OrderPlaced(order.id, principal.user_id, tuple(groups)))
        await db.commit()
    except IntegrityError as exc:  # the same key raced in from a parallel request
        await db.rollback()
        existing = await repo.find_by_key(db, principal.user_id, idempotency_key)
        if existing is None:
            raise _error("CHECKOUT_CONFLICT", "Please try again", 409) from exc
        return await _checkout_out(db, existing)
    except Exception:
        await db.rollback()
        raise
    _log("order placed", order_id=order.id, total=order.total, sellers=len(groups))
    return await _checkout_out(db, order, payment.id)


async def _checkout_out(
    db: AsyncSession, order: Order, payment_id: uuid.UUID | None = None
) -> CheckoutOut:
    out = await _order_out(db, order)
    payment = next((p for p in out.payments if p.id == payment_id), None) or out.payments[-1]
    step = (
        f"POST /api/v1/payments/{payment.id}/confirm" if payment.is_test else "redirect to provider"
    )
    if payment.status != "pending":
        step = "done"
    return CheckoutOut(order=out, payment=payment, next_step=step)


# ---------------------------------------------------------------- payment events


async def _locked_order(db: AsyncSession, order_id: uuid.UUID) -> Order | None:
    return await repo.get_order(db, order_id, lock=True)


async def on_payment_succeeded(db: AsyncSession, event: PaymentSucceeded) -> None:
    order = await _locked_order(db, event.order_id)
    if order is None:
        return
    if order.status == "cancelled":
        # Paid after the hold expired and the order was cancelled: give the money back.
        for s in await repo.seller_orders_of(db, order.id):
            await payments.refund_now(
                db,
                order_id=order.id,
                seller_order_id=s.id,
                amount=s.subtotal,
                reason="paid after cancellation",
            )
        return
    order.payment_status = "paid"
    await inventory.commit_reservations(db, order.id)
    parts = await repo.seller_orders_of(db, order.id)
    await publish(db, OrderPaid(order.id, order.user_id, tuple(s.store_id for s in parts)))


async def _cancel_unpaid(db: AsyncSession, order: Order, reason: str, back_to_cart: bool) -> None:
    await inventory.release_reservations(db, order.id)
    await payments.cancel_pending(db, order.id)
    parts = await repo.seller_orders_of(db, order.id)
    for s in parts:
        if s.status != "cancelled":
            _move(db, s, "cancelled", None, reason)
    order.status = "cancelled"
    order.cancel_reason = reason
    order.cancelled_at = _now()
    if back_to_cart:
        items = await repo.items_of(db, [s.id for s in parts])
        await cart.restore(
            db, order.user_id, [(i.variant_id, i.quantity) for i in items if i.variant_id]
        )
    await publish(db, OrderCancelled(order.id, order.user_id, reason))


async def on_payment_failed(db: AsyncSession, event: PaymentFailed) -> None:
    order = await _locked_order(db, event.order_id)
    if order is None or order.status == "cancelled":
        return
    order.payment_status = "failed"
    await _cancel_unpaid(db, order, "payment failed", back_to_cart=True)


async def on_refund_completed(db: AsyncSession, event: RefundCompleted) -> None:
    order = await _locked_order(db, event.order_id)
    if order is None:
        return
    if event.seller_order_id is not None:
        part = await repo.get_seller_order(db, event.seller_order_id, lock=True)
        if part is not None:
            part.refunded_amount += event.amount
            if part.status == "delivered" and part.refunded_amount >= part.subtotal:
                _move(db, part, "returned", None, "fully refunded")
    returned = await repo.return_by_refund(db, event.refund_id)
    if returned is not None:
        returned.status = "refunded"
    parts = await repo.seller_orders_of(db, order.id)
    refunded = sum((s.refunded_amount for s in parts), Decimal(0))
    order.payment_status = "refunded" if refunded >= order.total else "partially_refunded"
    _recompute(order, parts)


async def expire_unpaid(limit: int = 100) -> int:
    """Background job: cancels unpaid orders whose stock hold ran out."""
    done = 0
    async with get_sessionmaker()() as db:
        for order_id in await inventory.expired_reservation_orders(db, limit):
            order = await _locked_order(db, order_id)
            if order is None or order.payment_status not in ("pending", "unpaid", "failed"):
                continue
            if order.status != "cancelled":
                await _cancel_unpaid(db, order, "not paid in time", back_to_cart=True)
                done += 1
            else:
                await inventory.release_reservations(db, order_id)
        await db.commit()
    if done:
        _log("expired unpaid orders cancelled", count=done)
    return done


# ---------------------------------------------------------------- buyer


async def _own_order(db: AsyncSession, principal: Principal, order_id: uuid.UUID) -> Order:
    order = await repo.get_order(db, order_id, lock=True)
    if order is None or order.user_id != principal.user_id:
        raise _not_found()
    return order


async def list_orders(
    db: AsyncSession, principal: Principal, offset: int, limit: int
) -> list[OrderSummary]:
    out = []
    for o in await repo.orders_of(db, principal.user_id, offset, limit):
        summary = OrderSummary.model_validate(o)
        parts = await repo.seller_orders_of(db, o.id)
        summary.item_count = sum(i.quantity for i in await repo.items_of(db, [s.id for s in parts]))
        out.append(summary)
    return out


async def get_order(db: AsyncSession, principal: Principal, order_id: uuid.UUID) -> OrderOut:
    order = await repo.get_order(db, order_id)
    if order is None or (order.user_id != principal.user_id and not principal.has("orders.read")):
        raise _not_found()
    return await _order_out(db, order)


async def cancel_order(
    db: AsyncSession, principal: Principal, order_id: uuid.UUID, reason: str
) -> OrderOut:
    """The buyer cancels before anything shipped. A paid order is refunded at once."""
    order = await _own_order(db, principal, order_id)
    if order.status == "cancelled":
        raise _error("ALREADY_CANCELLED", "The order is already cancelled", 409)
    parts = list(await repo.seller_orders_of(db, order.id))
    if any(s.status not in ("new", "confirmed") for s in parts):
        raise _error("TOO_LATE", "Part of the order has shipped: ask for a return instead", 409)
    reason = reason or "cancelled by buyer"
    if order.payment_status == "paid":
        for s in parts:
            await _cancel_paid_part(db, order, s, principal.user_id, reason)
        order.status = "cancelled"
        order.cancel_reason = reason
        order.cancelled_at = _now()
        await publish(db, OrderCancelled(order.id, order.user_id, reason))
    else:
        await _cancel_unpaid(db, order, reason, back_to_cart=False)
    await db.commit()
    _log("order cancelled by buyer", order_id=order.id)
    return await _order_out(db, order)


async def _cancel_paid_part(
    db: AsyncSession, order: Order, part: SellerOrder, actor: uuid.UUID | None, reason: str
) -> None:
    """Paid seller order cancelled before shipping: stock back on the shelf, money back."""
    for item in await repo.items_of(db, [part.id]):
        if item.variant_id is not None:
            await inventory.return_to_stock(
                db, part.store_id, item.variant_id, item.quantity, f"cancelled {part.number}"
            )
    _move(db, part, "cancelled", actor, reason)
    left = part.subtotal - part.refunded_amount
    if left > 0:
        await payments.refund_now(
            db, order_id=order.id, seller_order_id=part.id, amount=left, reason=reason
        )


# ---------------------------------------------------------------- status machine


def _move(
    db: AsyncSession, part: SellerOrder, to: str, actor: uuid.UUID | None, note: str | None
) -> str:
    before = part.status
    part.status = to
    if to == "shipped":
        part.shipped_at = _now()
    elif to == "delivered":
        part.delivered_at = _now()
    db.add(
        OrderStatusHistory(
            id=uuid7(),
            seller_order_id=part.id,
            from_status=before,
            to_status=to,
            actor_id=actor,
            note=note,
        )
    )
    return before


def _recompute(order: Order, parts: Sequence[SellerOrder]) -> None:
    """Parent status from the seller orders."""
    statuses = {s.status for s in parts}
    if statuses <= {"cancelled"}:
        order.status = "cancelled"
    elif statuses <= {"delivered", "returned", "cancelled"}:
        order.status = "completed"
    elif statuses & {"shipped", "delivered", "returned"}:
        order.status = "partially_fulfilled"
    else:
        order.status = "placed"


async def _change_status(
    db: AsyncSession, part: SellerOrder, data: StatusIn, actor: uuid.UUID, *, override: bool
) -> None:
    order = await _locked_order(db, part.order_id)
    if order is None:
        raise _not_found()
    if data.status not in TRANSITIONS[part.status] and not override:
        raise _error("BAD_TRANSITION", f"Cannot go from {part.status} to {data.status}", 409)
    if data.status in ("confirmed", "shipped", "delivered") and order.payment_status != "paid":
        raise _error("NOT_PAID", "The order is not paid yet", 409)
    if data.status == "shipped" and data.tracking_number:
        part.tracking_number = data.tracking_number
    if data.status == "cancelled":
        if order.payment_status in ("paid", "partially_refunded"):
            await _cancel_paid_part(db, order, part, actor, data.note or "cancelled by seller")
        else:
            _move(db, part, "cancelled", actor, data.note)
        before = "cancelled"
    else:
        before = _move(db, part, data.status, actor, data.note)
    parts = list(await repo.seller_orders_of(db, order.id))
    if all(s.status == "cancelled" for s in parts) and order.payment_status not in (
        "paid",
        "partially_refunded",
        "refunded",
    ):
        await _cancel_unpaid(db, order, data.note or "cancelled by seller", back_to_cart=False)
    _recompute(order, parts)
    await publish(
        db,
        SellerOrderStatusChanged(
            part.id, order.id, part.store_id, order.user_id, part.number, before, part.status
        ),
    )


async def _seller_detail(db: AsyncSession, part: SellerOrder) -> SellerOrderDetail:
    order = await repo.get_order(db, part.order_id)
    assert order is not None  # noqa: S101 - FK
    (base,) = await _seller_parts(db, [part])
    return SellerOrderDetail(
        **base.model_dump(),
        order_id=order.id,
        order_number=order.number,
        payment_status=order.payment_status,
        shipping_address=order.shipping_address,
        commission=part.commission,
        created_at=part.created_at,
    )


async def _store_part(
    db: AsyncSession, access: StoreAccess, seller_order_id: uuid.UUID
) -> SellerOrder:
    part = await repo.get_seller_order(db, seller_order_id, lock=True)
    if part is None or part.store_id != access.store_id:
        raise _not_found()
    return part


async def store_orders(
    db: AsyncSession, access: StoreAccess, status: str | None, offset: int, limit: int
) -> list[SellerOrderDetail]:
    return [
        await _seller_detail(db, p)
        for p in await repo.store_orders(db, access.store_id, status, offset, limit)
    ]


async def store_order(
    db: AsyncSession, access: StoreAccess, seller_order_id: uuid.UUID
) -> SellerOrderDetail:
    return await _seller_detail(db, await _store_part(db, access, seller_order_id))


async def seller_set_status(
    db: AsyncSession, access: StoreAccess, seller_order_id: uuid.UUID, data: StatusIn
) -> SellerOrderDetail:
    part = await _store_part(db, access, seller_order_id)
    await _change_status(db, part, data, access.user_id, override=False)
    await db.commit()
    _log("seller order status", seller_order_id=part.id, status=part.status)
    return await _seller_detail(db, part)


async def staff_set_status(
    db: AsyncSession, principal: Principal, seller_order_id: uuid.UUID, data: StatusIn
) -> SellerOrderDetail:
    """Platform staff override (audited): any move except back from a final status."""
    part = await repo.get_seller_order(db, seller_order_id, lock=True)
    if part is None:
        raise _not_found()
    if part.status in ("cancelled", "returned"):
        raise _error("FINAL_STATUS", f"The order is already {part.status}", 409)
    await _change_status(db, part, data, principal.user_id, override=True)
    await db.commit()
    _log(
        "seller order status override",
        seller_order_id=part.id,
        status=part.status,
        actor=principal.user_id,
    )
    return await _seller_detail(db, part)


async def admin_orders(
    db: AsyncSession, status: str | None, offset: int, limit: int
) -> list[OrderSummary]:
    return [
        OrderSummary.model_validate(o)
        for o in await repo.orders_of(db, None, offset, limit, status)
    ]


# ---------------------------------------------------------------- returns


async def request_return(
    db: AsyncSession,
    principal: Principal,
    order_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ReturnIn,
) -> ReturnOut:
    order = await _own_order(db, principal, order_id)
    item = await repo.get_item(db, item_id)
    part = await repo.get_seller_order(db, item.seller_order_id) if item else None
    if item is None or part is None or part.order_id != order.id:
        raise _error("ITEM_NOT_FOUND", "Item not found in this order", 404)
    if part.status != "delivered" or part.delivered_at is None:
        raise _error("NOT_DELIVERED", "Returns are possible after delivery", 409)
    if _now() - part.delivered_at > timedelta(days=RETURN_DAYS):
        raise _error("RETURN_EXPIRED", f"Returns are accepted within {RETURN_DAYS} days", 409)
    asked = sum(
        r.quantity for r in await repo.returns_of_item(db, item.id) if r.status != "rejected"
    )
    if asked + data.quantity > item.quantity:
        raise _error("TOO_MANY", "More than you bought", 409)
    request = ReturnRequest(
        id=uuid7(),
        seller_order_id=part.id,
        order_item_id=item.id,
        user_id=principal.user_id,
        quantity=data.quantity,
        reason=data.reason,
        status="requested",
    )
    db.add(request)
    await db.commit()
    _log("return requested", return_id=request.id)
    return ReturnOut.model_validate(request)


async def my_returns(db: AsyncSession, principal: Principal) -> list[ReturnOut]:
    return [ReturnOut.model_validate(r) for r in await repo.returns_of_user(db, principal.user_id)]


async def store_returns(
    db: AsyncSession, access: StoreAccess, status: str | None
) -> list[ReturnOut]:
    return [
        ReturnOut.model_validate(r) for r in await repo.store_returns(db, access.store_id, status)
    ]


async def decide_return(
    db: AsyncSession, access: StoreAccess, return_id: uuid.UUID, data: ReturnDecisionIn
) -> ReturnOut:
    """approve -> the buyer sends it; receive -> stock back + refund request for finance."""
    request = await repo.get_return(db, return_id)
    part = await repo.get_seller_order(db, request.seller_order_id) if request else None
    if request is None or part is None or part.store_id != access.store_id:
        raise _error("RETURN_NOT_FOUND", "Return not found", 404)
    allowed = {"approve": ("requested",), "reject": ("requested",), "receive": ("approved",)}
    if request.status not in allowed[data.action]:
        raise _error("BAD_TRANSITION", f"The return is {request.status}", 409)
    request.decided_by = access.user_id
    request.decision_note = data.note
    if data.action == "reject":
        request.status = "rejected"
    elif data.action == "approve":
        request.status = "approved"
    else:
        item = await repo.get_item(db, request.order_item_id)
        assert item is not None  # noqa: S101 - FK
        if item.variant_id is not None:
            await inventory.return_to_stock(
                db, part.store_id, item.variant_id, request.quantity, f"return {part.number}"
            )
        refund = await payments.request_refund(
            db,
            order_id=part.order_id,
            seller_order_id=part.id,
            amount=item.unit_price * request.quantity,
            reason=f"return: {request.reason}"[:500],
            requested_by=access.user_id,
        )
        request.status = "received"
        request.refund_id = refund.id
    await db.commit()
    _log("return decided", return_id=request.id, action=data.action)
    return ReturnOut.model_validate(request)


# ---------------------------------------------------------------- for other modules


async def purchased_item(
    db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID
) -> uuid.UUID | None:
    """Order item proving the user bought and received the product (reviews, buyer photos)."""
    return await repo.purchased(db, user_id, product_id)


# ---------------------------------------------------------------- statistics (analytics, home)


@dataclass(frozen=True)
class DaySales:
    day: date
    orders: int
    revenue: Decimal
    commission: Decimal


async def best_sellers(
    db: AsyncSession, days: int, limit: int, store_id: uuid.UUID | None = None
) -> list[tuple[uuid.UUID, int]]:
    """(product_id, units sold) in paid, not cancelled orders of the last ``days``."""
    return await repo.best_sellers(db, datetime.now(UTC) - timedelta(days=days), limit, store_id)


async def store_sales(
    db: AsyncSession, store_id: uuid.UUID, since: datetime, until: datetime
) -> list[DaySales]:
    return [DaySales(*row) for row in await repo.store_sales(db, store_id, since, until)]


async def store_order_counts(
    db: AsyncSession, store_id: uuid.UUID, since: datetime, until: datetime
) -> dict[str, int]:
    """Seller orders by status created in the period (all, paid or not)."""
    return await repo.store_order_counts(db, store_id, since, until)


async def product_sales(
    db: AsyncSession, store_id: uuid.UUID, since: datetime, until: datetime
) -> dict[uuid.UUID, tuple[int, Decimal]]:
    """product_id -> (units, revenue)."""
    return await repo.product_sales(db, store_id, since, until)


async def bought_by_user(db: AsyncSession, user_id: uuid.UUID, limit: int = 20) -> list[uuid.UUID]:
    return await repo.bought_by_user(db, user_id, limit)
