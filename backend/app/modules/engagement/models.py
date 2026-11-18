"""Tables of the `engagement` module: favourites and product views."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey


class Favorite(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "favorites"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"),
        Index("ix_favorites_product", "product_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )


class ProductView(UUIDPrimaryKey, Base):
    """One counted view. ``viewer`` is the user id or a hash of the guest's device id."""

    __tablename__ = "product_views"
    __table_args__ = (
        Index("ix_product_views_product_viewed", "product_id", "viewed_at"),
        Index("ix_product_views_store_viewed", "store_id", "viewed_at"),
        Index("ix_product_views_viewer_viewed", "viewer", "viewed_at"),
        Index("ix_product_views_viewed", "viewed_at"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    store_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    viewer: Mapped[str] = mapped_column(String(64))
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
