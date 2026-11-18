"""Tables of the `payments` module (docs/architecture/03-database-er.md, 3.3).

Card data never reaches this backend: real providers use their own payment page; only the
provider's payment id and its answers (without card data) are stored. ``ledger_entries``
is insert-only bookkeeping: sale, platform commission, refund, payout.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

PAYMENT_STATUSES = ("created", "pending", "succeeded", "failed", "cancelled")
REFUND_STATUSES = ("requested", "approved", "processing", "completed", "failed", "rejected")
LEDGER_TYPES = ("sale", "commission", "refund", "commission_refund", "payout")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Payment(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "payments"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(_in("status", PAYMENT_STATUSES), name="status"),
        CheckConstraint("amount > 0", name="amount"),
        UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_id"),
    )

    # The parent order. No foreign key: payments does not depend on the orders tables.
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[str] = mapped_column(String(16))
    provider_payment_id: Mapped[str] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="UZS", server_default="UZS")
    status: Mapped[str] = mapped_column(String(10), default="pending")
    is_test: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # How the money splits between stores: [{"store_id", "seller_order_id", "amount",
    # "commission"}]. Used for ledger entries and refunds.
    splits: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PaymentAttempt(UUIDPrimaryKey, Base):
    __tablename__ = "payment_attempts"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"), index=True
    )
    result: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16))  # api | webhook | job
    provider_response: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Refund(UUIDPrimaryKey, Timestamps, Base):
    """Money back to the buyer. Who initiated it can never approve it (separation of duties)."""

    __tablename__ = "refunds"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(_in("status", REFUND_STATUSES), name="status"),
        CheckConstraint("amount > 0", name="amount"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    seller_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    reason: Mapped[str] = mapped_column(String(500), default="", server_default="")
    status: Mapped[str] = mapped_column(String(12), default="requested")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    provider_refund_id: Mapped[str | None] = mapped_column(String(128))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookEvent(UUIDPrimaryKey, Base):
    """Every provider notification once: a repeated ``event_id`` is ignored."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_events_event"),)

    provider: Mapped[str] = mapped_column(String(16))
    event_id: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LedgerEntry(UUIDPrimaryKey, Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint(_in("type", LEDGER_TYPES), name="type"),
        Index("ix_ledger_entries_store_created", "store_id", "created_at"),
    )

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    seller_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    refund_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    type: Mapped[str] = mapped_column(String(20))
    # Signed from the store's point of view: sale +, commission -, refund -.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="UZS", server_default="UZS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
