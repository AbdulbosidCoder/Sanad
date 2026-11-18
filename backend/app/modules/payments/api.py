"""HTTP endpoints of the `payments` module. Business logic lives in service.py."""

import uuid
from typing import Literal

from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_permission, require_sensitive_action
from app.core.db import get_session
from app.core.modules import module_router
from app.modules.payments import service
from app.modules.payments.schemas import ConfirmIn, LedgerOut, PaymentOut, RefundOut

router = module_router("payments")

Offset = Query(0, ge=0)
Limit = Query(50, ge=1, le=200)


@router.get("/payments/methods")
async def methods() -> list[str]:
    """Payment methods enabled right now (V1: "fake")."""
    return service.available_providers()


@router.get("/payments/{payment_id}")
async def get_payment(
    payment_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> PaymentOut:
    return await service.get_payment(db, principal, payment_id)


@router.post("/payments/{payment_id}/confirm")
async def confirm(
    payment_id: uuid.UUID,
    data: ConfirmIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> PaymentOut:
    """Test payments only: simulate the buyer paying (``succeeded``) or the bank declining."""
    return await service.confirm_fake(db, principal, payment_id, data.outcome)


@router.post("/webhooks/payments/{provider}")
async def webhook(
    provider: str, request: Request, db: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    """Provider notifications. Signed; repeats are ignored."""
    body = await request.body()
    result = await service.handle_webhook(db, provider, request.headers, body)
    return {"result": result}


# ---------------------------------------------------------------- admin / finance


@router.get("/admin/payments")
async def list_payments(
    status: Literal["pending", "succeeded", "failed", "cancelled"] | None = None,
    offset: int = Offset,
    limit: int = Limit,
    _: Principal = Depends(require_permission("payments.read")),
    db: AsyncSession = Depends(get_session),
) -> list[PaymentOut]:
    return await service.list_payments(db, status, offset, limit)


@router.get("/admin/refunds")
async def list_refunds(
    status: Literal["requested", "completed", "failed", "rejected"] | None = None,
    offset: int = Offset,
    limit: int = Limit,
    _: Principal = Depends(require_permission("payments.read")),
    db: AsyncSession = Depends(get_session),
) -> list[RefundOut]:
    return await service.list_refunds(db, status, offset, limit)


@router.post("/admin/refunds/{refund_id}/approve")
async def approve_refund(
    refund_id: uuid.UUID,
    principal: Principal = Depends(require_sensitive_action("refunds.approve")),
    db: AsyncSession = Depends(get_session),
) -> RefundOut:
    """Sends the money back. Not allowed for the person who requested the refund."""
    return await service.approve_refund(db, principal, refund_id)


@router.post("/admin/refunds/{refund_id}/reject")
async def reject_refund(
    refund_id: uuid.UUID,
    principal: Principal = Depends(require_sensitive_action("refunds.approve")),
    db: AsyncSession = Depends(get_session),
) -> RefundOut:
    return await service.reject_refund(db, principal, refund_id)


@router.get("/admin/ledger")
async def ledger(
    store_id: uuid.UUID | None = None,
    offset: int = Offset,
    limit: int = Limit,
    _: Principal = Depends(require_permission("payments.read")),
    db: AsyncSession = Depends(get_session),
) -> list[LedgerOut]:
    return await service.ledger(db, store_id, offset, limit)
