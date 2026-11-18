"""Tables of the `reviews` module.

A review can be written only for a product the user bought and received
(``order_item_id`` is the proof), one per user and product. ``fit`` says how the size
fits — important for shoes and clothes.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

FITS = ("small", "true", "large")


class Review(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "reviews"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_reviews_user_product"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating"),
        CheckConstraint("status IN ('published', 'hidden')", name="status"),
        CheckConstraint("fit IS NULL OR fit IN ('small', 'true', 'large')", name="fit"),
        Index("ix_reviews_product_status_created", "product_id", "status", "created_at"),
        Index("ix_reviews_store_created", "store_id", "created_at"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    order_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    rating: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    fit: Mapped[str | None] = mapped_column(String(5))
    status: Mapped[str] = mapped_column(String(10), default="published", server_default="published")
    hidden_reason: Mapped[str | None] = mapped_column(String(300))
    seller_reply: Mapped[str | None] = mapped_column(Text)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
