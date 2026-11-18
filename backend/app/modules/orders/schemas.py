"""Request and response bodies of the `orders` API."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.payments.service import PaymentOut

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CheckoutIn(_In):
    address_id: uuid.UUID | None = Field(None, description="default address if omitted")
    payment_method: str = "fake"


class PreviewGroup(BaseModel):
    store_id: uuid.UUID
    store_name: str
    item_count: int
    subtotal: Decimal


class PreviewOut(BaseModel):
    groups: list[PreviewGroup]
    shipping: Decimal = Decimal(0)
    total: Decimal
    currency: str = "UZS"
    shipping_address: dict[str, Any] | None
    payment_methods: list[str]


class ItemOut(_Out):
    id: uuid.UUID
    variant_id: uuid.UUID | None
    product_id: uuid.UUID | None
    title: str
    sku: str
    attributes: dict[str, str]
    cover_url: str | None
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class HistoryOut(_Out):
    from_status: str | None
    to_status: str
    note: str | None
    created_at: datetime


class SellerOrderOut(_Out):
    id: uuid.UUID
    number: str
    store_id: uuid.UUID
    store_name: str = ""
    subtotal: Decimal
    status: str
    tracking_number: str | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    refunded_amount: Decimal
    items: list[ItemOut] = Field(default_factory=list)
    history: list[HistoryOut] = Field(default_factory=list)


class OrderOut(_Out):
    id: uuid.UUID
    number: str
    status: str
    payment_status: str
    total: Decimal
    currency: str
    shipping_address: dict[str, Any]
    cancel_reason: str | None
    created_at: datetime
    seller_orders: list[SellerOrderOut] = Field(default_factory=list)
    payments: list[PaymentOut] = Field(default_factory=list)


class OrderSummary(_Out):
    id: uuid.UUID
    number: str
    status: str
    payment_status: str
    total: Decimal
    currency: str
    item_count: int = 0
    created_at: datetime


class CheckoutOut(BaseModel):
    order: OrderOut
    payment: PaymentOut
    next_step: str = Field(
        description="What the client does next. Test payments: POST /payments/{id}/confirm"
    )


class CancelIn(_In):
    reason: Note = ""


SellerStatus = Literal["confirmed", "shipped", "delivered", "cancelled"]


class StatusIn(_In):
    status: SellerStatus
    tracking_number: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)] | None
    ) = None
    note: Note | None = None


class SellerOrderDetail(SellerOrderOut):
    order_id: uuid.UUID
    order_number: str
    payment_status: str
    shipping_address: dict[str, Any]
    commission: Decimal
    created_at: datetime


class ReturnIn(_In):
    quantity: Annotated[int, Field(ge=1, le=99)] = 1
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]


class ReturnDecisionIn(_In):
    action: Literal["approve", "reject", "receive"]
    note: Note | None = None


class ReturnOut(_Out):
    id: uuid.UUID
    seller_order_id: uuid.UUID
    order_item_id: uuid.UUID
    quantity: int
    reason: str
    status: str
    decision_note: str | None
    refund_id: uuid.UUID | None
    created_at: datetime
