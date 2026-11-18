"""Tables of the `orders` module (docs/architecture/03-database-er.md, 3.3; ADR 0003).

One checkout = one ``orders`` row (what the buyer paid) split into one ``seller_orders`` row
per store (what each seller ships). Order status, payment status and every seller order's
status are independent. Prices, titles and the address are *copied* into the order, so
later catalog changes never rewrite history.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

ORDER_STATUSES = ("placed", "partially_fulfilled", "completed", "cancelled")
PAYMENT_STATUSES = ("unpaid", "pending", "paid", "partially_refunded", "refunded", "failed")
SELLER_ORDER_STATUSES = ("new", "confirmed", "shipped", "delivered", "cancelled", "returned")
RETURN_STATUSES = ("requested", "approved", "rejected", "received", "refunded")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Order(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "orders"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(_in("status", ORDER_STATUSES), name="status"),
        CheckConstraint(_in("payment_status", PAYMENT_STATUSES), name="payment_status"),
        UniqueConstraint("user_id", "idempotency_key", name="uq_orders_idempotency"),
        Index("ix_orders_user_created", "user_id", "created_at"),
    )

    number: Mapped[str] = mapped_column(String(20), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    shipping_address: Mapped[dict[str, Any]] = mapped_column(JSONB)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="UZS", server_default="UZS")
    status: Mapped[str] = mapped_column(String(20), default="placed")
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid")
    payment_provider: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SellerOrder(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "seller_orders"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(_in("status", SELLER_ORDER_STATUSES), name="status"),
        Index("ix_seller_orders_store_status", "store_id", "status", "created_at"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="RESTRICT")
    )
    number: Mapped[str] = mapped_column(String(24), unique=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Platform commission, fixed at checkout from the store's commission_rate.
    commission: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(12), default="new")
    tracking_number: Mapped[str | None] = mapped_column(String(64))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal(0), server_default="0"
    )


class OrderItem(UUIDPrimaryKey, Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity"),)

    seller_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seller_orders.id", ondelete="CASCADE"), index=True
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="SET NULL"), index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    # Snapshot at checkout.
    title: Mapped[str] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(64))
    attributes: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    cover_url: Mapped[str | None] = mapped_column(String(1000))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    quantity: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))


class OrderStatusHistory(UUIDPrimaryKey, Base):
    __tablename__ = "order_status_history"

    seller_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seller_orders.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(12))
    to_status: Mapped[str] = mapped_column(String(12))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ReturnRequest(UUIDPrimaryKey, Timestamps, Base):
    """A buyer wants to send a delivered item back."""

    __tablename__ = "return_requests"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(_in("status", RETURN_STATUSES), name="status"),
        CheckConstraint("quantity > 0", name="quantity"),
    )

    seller_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seller_orders.id", ondelete="CASCADE"), index=True
    )
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("order_items.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(10), default="requested")
    decision_note: Mapped[str | None] = mapped_column(String(500))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    refund_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
