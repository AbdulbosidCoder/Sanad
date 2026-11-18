"""Request and response bodies of the `payments` API."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    provider: str
    amount: Decimal
    currency: str
    status: str
    is_test: bool
    paid_at: datetime | None
    created_at: datetime


class ConfirmIn(BaseModel):
    """Fake provider only: which outcome to simulate."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["succeeded", "failed"] = "succeeded"


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payment_id: uuid.UUID
    seller_order_id: uuid.UUID | None
    store_id: uuid.UUID | None
    amount: Decimal
    reason: str
    status: str
    requested_by: uuid.UUID | None
    approved_by: uuid.UUID | None
    completed_at: datetime | None
    created_at: datetime


class LedgerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payment_id: uuid.UUID
    store_id: uuid.UUID
    seller_order_id: uuid.UUID | None
    type: str
    amount: Decimal
    currency: str
    created_at: datetime
