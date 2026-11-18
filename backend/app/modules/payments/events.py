"""Domain events of the `payments` module.

Emits: PaymentSucceeded, PaymentFailed, RefundCompleted
Listens to: nothing
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PaymentSucceeded:
    payment_id: uuid.UUID
    order_id: uuid.UUID


@dataclass(frozen=True)
class PaymentFailed:
    payment_id: uuid.UUID
    order_id: uuid.UUID
    reason: str


@dataclass(frozen=True)
class RefundCompleted:
    refund_id: uuid.UUID
    payment_id: uuid.UUID
    order_id: uuid.UUID
    seller_order_id: uuid.UUID | None
    amount: Decimal
