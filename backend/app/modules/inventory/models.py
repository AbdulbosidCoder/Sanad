"""Tables of the `inventory` module (docs/architecture/03-database-er.md, 3.2).

One ``inventory`` row per product variant. ``reserved`` is stock held for unpaid orders
(stage 5); what can be sold is ``on_hand - reserved``. Every change is written to
``stock_movements``, so a wrong number can always be traced back.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

MOVEMENT_REASONS = ("manual", "seed", "sale", "return", "cancel")


class Inventory(Timestamps, Base):
    __tablename__ = "inventory"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint("on_hand >= 0", name="on_hand"),
        CheckConstraint("reserved >= 0 AND reserved <= on_hand", name="reserved"),
        CheckConstraint("low_stock_threshold >= 0", name="threshold"),
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE"), primary_key=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE"), index=True
    )
    on_hand: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reserved: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5, server_default="5")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class StockMovement(UUIDPrimaryKey, Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            f"reason IN ({', '.join(repr(r) for r in MOVEMENT_REASONS)})", name="reason"
        ),
        Index("ix_stock_movements_variant_created", "variant_id", "created_at"),
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE")
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE")
    )
    delta: Mapped[int] = mapped_column(Integer)
    on_hand_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None] = mapped_column(String(255))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


RESERVATION_STATUSES = ("active", "committed", "released")


class StockReservation(UUIDPrimaryKey, Timestamps, Base):
    """Stock held for an unpaid order. Paid -> ``committed`` (stock leaves the shelf);
    payment failed, order cancelled or time ran out -> ``released``."""

    __tablename__ = "stock_reservations"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity"),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in RESERVATION_STATUSES)})", name="status"
        ),
        Index("ix_stock_reservations_order", "order_id"),
        Index("ix_stock_reservations_active_expiry", "status", "expires_at"),
    )

    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE")
    )
    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="CASCADE")
    )
    # The parent order; no foreign key, so inventory does not depend on the orders tables.
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="active", server_default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
