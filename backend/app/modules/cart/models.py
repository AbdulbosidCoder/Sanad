"""Tables of the `cart` module (docs/architecture/03-database-er.md, 3.3).

A cart belongs to a signed-in user, or to a guest identified by a random token the
client keeps (``X-Cart-Token``); only the token's SHA-256 is stored. After sign-in the
guest cart is merged into the user's one (``POST /cart/merge``).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

MAX_QUANTITY = 99


class Cart(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "carts"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint("(user_id IS NULL) <> (guest_token_hash IS NULL)", name="one_owner"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    guest_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (CheckConstraint(f"quantity BETWEEN 1 AND {MAX_QUANTITY}", name="quantity"),)

    cart_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("carts.id", ondelete="CASCADE"), primary_key=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="CASCADE"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
