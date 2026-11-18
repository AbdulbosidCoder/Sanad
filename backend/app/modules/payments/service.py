"""Business logic of the `payments` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

The orders module only calls ``create_payment`` and ``request_refund``/``refund_now``; it
learns the outcome from the ``PaymentSucceeded`` / ``PaymentFailed`` / ``RefundCompleted``
events. Which provider is behind a payment is invisible to it.
"""

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import AppError
from app.core.events import publish
from app.core.models import uuid7
from app.modules.payments import repository as repo
from app.modules.payments.events import PaymentFailed, PaymentSucceeded, RefundCompleted
from app.modules.payments.models import LedgerEntry, Payment, PaymentAttempt, Refund
from app.modules.payments.providers import (
    FakeProvider,
    InvalidWebhook,
    PaymentProvider,
    PaymentRequest,
    registry,
)
from app.modules.payments.schemas import LedgerOut, RefundOut
from app.modules.payments.schemas import PaymentOut as PaymentOut  # used by orders

MODULE = "payments"
FINAL = ("succeeded", "failed", "cancelled")
CENT = Decimal("0.01")

logger = logging.getLogger("app.modules.payments")


def _error(code: str, detail: str, status: int) -> AppError:
    return AppError(MODULE, code, detail, status=status)


def _log(msg: str, **fields: object) -> None:
    logger.info(msg, extra={"extra_fields": {k: str(v) for k, v in fields.items()}})


def _provider(code: str) -> PaymentProvider:
    provider = registry().get(code)
    if provider is None:
        raise _error("PROVIDER_UNAVAILABLE", f"Payment method '{code}' is not available", 400)
    return provider


def sign_fake_webhook(body: bytes) -> str:
    """Signature the fake provider puts on its webhooks (tests, local tools)."""
    return FakeProvider.sign(body)


def available_providers() -> list[str]:
    return sorted(registry())


# ---------------------------------------------------------------- payments


@dataclass(frozen=True)
class Split:
    store_id: uuid.UUID
    seller_order_id: uuid.UUID
    amount: Decimal
    commission: Decimal


async def create_payment(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    splits: list[Split],
    provider_code: str,
    description: str,
) -> PaymentOut:
    """Opens a payment for an order (no commit: part of the checkout transaction)."""
    provider = _provider(provider_code)
    answer = await provider.create_payment(PaymentRequest(amount, currency, description))
    payment = Payment(
        id=uuid7(),
        order_id=order_id,
        user_id=user_id,
        provider=provider.code,
        provider_payment_id=answer.provider_payment_id,
        amount=amount,
        currency=currency,
        status="pending",
        is_test=provider.is_test,
        splits=[
            {
                "store_id": str(s.store_id),
                "seller_order_id": str(s.seller_order_id),
                "amount": str(s.amount),
                "commission": str(s.commission),
            }
            for s in splits
        ],
    )
    db.add(payment)
    await db.flush()
    if answer.status != "pending":
        await _apply(db, payment, answer.status, {"create": answer.status}, "api")
    return PaymentOut.model_validate(payment)


async def _apply(
    db: AsyncSession, payment: Payment, status: str, response: dict[str, Any], source: str
) -> bool:
    """Moves a payment to its final status once. False if it was already final."""
    if payment.status in FINAL:
        return False
    db.add(
        PaymentAttempt(
            id=uuid7(),
            payment_id=payment.id,
            result=status,
            source=source,
            provider_response=response,
        )
    )
    payment.status = status
    if status == "succeeded":
        payment.paid_at = datetime.now(UTC)
        for s in payment.splits:
            store_id = uuid.UUID(s["store_id"])
            seller_order_id = uuid.UUID(s["seller_order_id"])
            db.add(
                LedgerEntry(
                    id=uuid7(),
                    payment_id=payment.id,
                    store_id=store_id,
                    seller_order_id=seller_order_id,
                    type="sale",
                    amount=Decimal(s["amount"]),
                    currency=payment.currency,
                )
            )
            db.add(
                LedgerEntry(
                    id=uuid7(),
                    payment_id=payment.id,
                    store_id=store_id,
                    seller_order_id=seller_order_id,
                    type="commission",
                    amount=-Decimal(s["commission"]),
                    currency=payment.currency,
                )
            )
        await db.flush()
        await publish(db, PaymentSucceeded(payment.id, payment.order_id))
    elif status == "failed":
        await db.flush()
        await publish(db, PaymentFailed(payment.id, payment.order_id, str(response)[:200]))
    _log("payment status", payment_id=payment.id, status=status, source=source)
    return True


async def get_payment(db: AsyncSession, principal: Principal, payment_id: uuid.UUID) -> PaymentOut:
    payment = await repo.lock_payment(db, payment_id)
    if payment is None or (
        payment.user_id != principal.user_id and not principal.has("payments.read")
    ):
        raise _error("PAYMENT_NOT_FOUND", "Payment not found", 404)
    return PaymentOut.model_validate(payment)


async def confirm_fake(
    db: AsyncSession, principal: Principal, payment_id: uuid.UUID, outcome: str
) -> PaymentOut:
    """The buyer 'pays' a test payment and picks the result."""
    payment = await repo.lock_payment(db, payment_id)
    if payment is None or payment.user_id != principal.user_id:
        raise _error("PAYMENT_NOT_FOUND", "Payment not found", 404)
    if payment.provider != FakeProvider.code:
        raise _error("NOT_A_TEST_PAYMENT", "Only test payments are confirmed this way", 409)
    _provider(payment.provider)  # still enabled?
    if not await _apply(db, payment, outcome, {"confirm": outcome}, "api"):
        raise _error("PAYMENT_FINAL", f"The payment is already {payment.status}", 409)
    await db.commit()
    return PaymentOut.model_validate(payment)


async def handle_webhook(
    db: AsyncSession, provider_code: str, headers: Mapping[str, str], body: bytes
) -> str:
    """Provider notification. Checks the signature, ignores repeats. Returns what happened."""
    provider = _provider(provider_code)
    try:
        event = provider.verify_webhook(headers, body)
    except InvalidWebhook as exc:
        raise _error("BAD_WEBHOOK", "Invalid webhook", 400) from exc
    if not await repo.remember_webhook(db, provider.code, event.event_id, event.payload):
        return "duplicate"
    payment = await repo.lock_by_provider_id(db, provider.code, event.provider_payment_id)
    if payment is None:
        await db.commit()
        return "unknown_payment"
    applied = await _apply(db, payment, event.status, event.payload, "webhook")
    await db.commit()
    return "applied" if applied else "already_final"


async def payments_of_order(db: AsyncSession, order_id: uuid.UUID) -> list[PaymentOut]:
    return [PaymentOut.model_validate(p) for p in await repo.payments_of_order(db, order_id)]


async def cancel_pending(db: AsyncSession, order_id: uuid.UUID) -> None:
    """The order was cancelled before payment: its open payments are closed (no commit)."""
    for p in await repo.payments_of_order(db, order_id):
        locked = await repo.lock_payment(db, p.id)
        if locked is not None and locked.status not in FINAL:
            locked.status = "cancelled"
            db.add(
                PaymentAttempt(
                    id=uuid7(),
                    payment_id=locked.id,
                    result="cancelled",
                    source="api",
                    provider_response={},
                )
            )


async def list_payments(
    db: AsyncSession, status: str | None, offset: int, limit: int
) -> list[PaymentOut]:
    return [
        PaymentOut.model_validate(p) for p in await repo.list_payments(db, status, offset, limit)
    ]


# ---------------------------------------------------------------- refunds


async def _paid_payment(db: AsyncSession, order_id: uuid.UUID) -> Payment:
    for p in await repo.payments_of_order(db, order_id):
        if p.status == "succeeded":
            locked = await repo.lock_payment(db, p.id)
            if locked is not None:
                return locked
    raise _error("NOT_PAID", "The order has no successful payment", 409)


def _split(payment: Payment, seller_order_id: uuid.UUID) -> dict[str, str]:
    for s in payment.splits:
        if s["seller_order_id"] == str(seller_order_id):
            return s
    raise _error("SPLIT_NOT_FOUND", "This seller order is not part of the payment", 404)


async def request_refund(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    seller_order_id: uuid.UUID,
    amount: Decimal,
    reason: str,
    requested_by: uuid.UUID | None,
) -> RefundOut:
    """Creates a refund that waits for finance approval (no commit)."""
    payment = await _paid_payment(db, order_id)
    split = _split(payment, seller_order_id)
    already = sum(
        (
            r.amount
            for r in await repo.refunds_of_payment(db, payment.id)
            if r.seller_order_id == seller_order_id and r.status not in ("failed", "rejected")
        ),
        Decimal(0),
    )
    if amount <= 0 or already + amount > Decimal(split["amount"]):
        raise _error("REFUND_TOO_BIG", "More than what is left to refund for this order", 409)
    refund = Refund(
        id=uuid7(),
        payment_id=payment.id,
        seller_order_id=seller_order_id,
        store_id=uuid.UUID(split["store_id"]),
        amount=amount,
        reason=reason,
        status="requested",
        requested_by=requested_by,
    )
    db.add(refund)
    await db.flush()
    _log("refund requested", refund_id=refund.id, amount=amount)
    return RefundOut.model_validate(refund)


async def _execute(db: AsyncSession, refund: Refund, approved_by: uuid.UUID | None) -> None:
    payment = await repo.lock_payment(db, refund.payment_id)
    if payment is None:
        raise _error("PAYMENT_NOT_FOUND", "Payment not found", 404)
    refund.status = "processing"
    refund.approved_by = approved_by
    answer = await _provider(payment.provider).refund(payment.provider_payment_id, refund.amount)
    refund.provider_refund_id = answer.provider_refund_id
    if answer.status != "completed":
        refund.status = "failed"
        return
    refund.status = "completed"
    refund.completed_at = datetime.now(UTC)
    split = _split(payment, refund.seller_order_id) if refund.seller_order_id else None
    if split is not None and refund.store_id is not None:
        share = (refund.amount / Decimal(split["amount"])) * Decimal(split["commission"])
        share = share.quantize(CENT, rounding=ROUND_HALF_UP)
        db.add(
            LedgerEntry(
                id=uuid7(),
                payment_id=payment.id,
                store_id=refund.store_id,
                seller_order_id=refund.seller_order_id,
                refund_id=refund.id,
                type="refund",
                amount=-refund.amount,
                currency=payment.currency,
            )
        )
        db.add(
            LedgerEntry(
                id=uuid7(),
                payment_id=payment.id,
                store_id=refund.store_id,
                seller_order_id=refund.seller_order_id,
                refund_id=refund.id,
                type="commission_refund",
                amount=share,
                currency=payment.currency,
            )
        )
    await db.flush()
    await publish(
        db,
        RefundCompleted(
            refund.id, payment.id, payment.order_id, refund.seller_order_id, refund.amount
        ),
    )
    _log("refund completed", refund_id=refund.id, amount=refund.amount)


async def refund_now(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    seller_order_id: uuid.UUID,
    amount: Decimal,
    reason: str,
) -> RefundOut:
    """Automatic refund with no human decision (buyer cancels a paid order before it ships).
    No commit."""
    out = await request_refund(
        db,
        order_id=order_id,
        seller_order_id=seller_order_id,
        amount=amount,
        reason=reason,
        requested_by=None,
    )
    refund = await repo.get_refund(db, out.id, lock=True)
    assert refund is not None  # noqa: S101 - just created
    await _execute(db, refund, None)
    return RefundOut.model_validate(refund)


async def approve_refund(db: AsyncSession, approver: Principal, refund_id: uuid.UUID) -> RefundOut:
    """Finance approves and the money goes back. The requester cannot approve their own refund."""
    refund = await repo.get_refund(db, refund_id, lock=True)
    if refund is None:
        raise _error("REFUND_NOT_FOUND", "Refund not found", 404)
    if refund.status != "requested":
        raise _error("REFUND_DECIDED", f"The refund is already {refund.status}", 409)
    if refund.requested_by == approver.user_id:
        raise _error("SAME_PERSON", "Whoever requested a refund cannot approve it", 403)
    await _execute(db, refund, approver.user_id)
    await db.commit()
    return RefundOut.model_validate(refund)


async def reject_refund(db: AsyncSession, approver: Principal, refund_id: uuid.UUID) -> RefundOut:
    refund = await repo.get_refund(db, refund_id, lock=True)
    if refund is None:
        raise _error("REFUND_NOT_FOUND", "Refund not found", 404)
    if refund.status != "requested":
        raise _error("REFUND_DECIDED", f"The refund is already {refund.status}", 409)
    refund.status = "rejected"
    refund.approved_by = approver.user_id
    await db.commit()
    return RefundOut.model_validate(refund)


async def list_refunds(
    db: AsyncSession, status: str | None, offset: int, limit: int
) -> list[RefundOut]:
    return [RefundOut.model_validate(r) for r in await repo.list_refunds(db, status, offset, limit)]


async def ledger(
    db: AsyncSession, store_id: uuid.UUID | None, offset: int, limit: int
) -> list[LedgerOut]:
    return [LedgerOut.model_validate(e) for e in await repo.ledger(db, store_id, offset, limit)]


@dataclass(frozen=True)
class StoreBalance:
    sales: Decimal
    commission: Decimal
    refunds: Decimal
    net: Decimal


async def store_balance(db: AsyncSession, store_id: uuid.UUID) -> StoreBalance:
    """What the store earned: sales - commission - refunds (+ refunded commission)."""
    sales = commission = refunds = Decimal(0)
    for e in await repo.ledger_of_store(db, store_id):
        if e.type == "sale":
            sales += e.amount
        elif e.type in ("commission", "commission_refund"):
            commission -= e.amount
        elif e.type == "refund":
            refunds -= e.amount
    return StoreBalance(sales, commission, refunds, sales - commission - refunds)
