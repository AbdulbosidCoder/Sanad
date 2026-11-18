"""Domain events of the `orders` module.

Emits: OrderPlaced, OrderPaid, OrderCancelled, SellerOrderStatusChanged
Listens to: PaymentSucceeded, PaymentFailed, RefundCompleted
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class OrderPlaced:
    order_id: uuid.UUID
    user_id: uuid.UUID
    store_ids: tuple[uuid.UUID, ...]
    number: str = ""


@dataclass(frozen=True)
class OrderPaid:
    order_id: uuid.UUID
    user_id: uuid.UUID
    store_ids: tuple[uuid.UUID, ...]
    number: str = ""


@dataclass(frozen=True)
class OrderCancelled:
    order_id: uuid.UUID
    user_id: uuid.UUID
    reason: str
    number: str = ""


@dataclass(frozen=True)
class SellerOrderStatusChanged:
    seller_order_id: uuid.UUID
    order_id: uuid.UUID
    store_id: uuid.UUID
    user_id: uuid.UUID
    number: str
    from_status: str
    to_status: str
