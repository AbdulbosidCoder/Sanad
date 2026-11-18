"""Tables of the `catalog` module (docs/architecture/03-database-er.md, 3.2).

Photos: a product shows real photos from every side. The seller uploads them per *angle*
(``PHOTO_ANGLES``); buyers add their own photos, which are shown after moderation. Every
photo has an ``ai_check`` field reserved for the future authenticity check.

``min_price`` and ``in_stock`` on products are summaries of the variants, kept up to date
by the service, so the catalog can filter and sort without joining other modules' tables.
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
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

LOCALES = ("uz", "ru", "en")
PRODUCT_STATUSES = ("draft", "active", "archived", "blocked")
# The seven sides a seller photographs (left, right, top, sole, inside, back, label).
PHOTO_ANGLES = ("left", "right", "top", "sole", "inside", "back", "label")
IMAGE_ANGLES = (*PHOTO_ANGLES, "other")
IMAGE_SOURCES = ("seller", "buyer")
IMAGE_STATUSES = ("pending", "approved", "rejected")
AI_CHECKS = ("unchecked", "passed", "suspicious")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _jsonb_object() -> Any:
    return text("'{}'::jsonb")


class Category(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "categories"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    # {"uz": "Krossovkalar", "ru": "Кроссовки", "en": "Sneakers"}; edited by admins.
    names: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Brand(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "brands"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    # The real logo is uploaded by an admin (trademark); empty = show the name as text.
    logo_url: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Product(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "products"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(_in("status", PRODUCT_STATUSES), name="status"),
        CheckConstraint(_in("source_locale", LOCALES), name="source_locale"),
        CheckConstraint("rating_avg >= 0 AND rating_avg <= 5", name="rating_avg"),
        Index("ix_products_listing", "status", "category_id", "brand_id"),
        Index("ix_products_store_status", "store_id", "status"),
    )

    store_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stores.id", ondelete="RESTRICT")
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT")
    )
    brand_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("brands.id", ondelete="RESTRICT")
    )
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    source_locale: Mapped[str] = mapped_column(String(2), default="ru")
    # Original text in source_locale. Translations to the other languages: i18n module (stage 3).
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    specifications: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=_jsonb_object()
    )
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    moderation_note: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Summaries of the variants (see module docstring).
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="UZS", server_default="UZS")
    in_stock: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # Filled by the reviews module later.
    rating_avg: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal(0), server_default="0"
    )
    rating_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ProductVariant(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "product_variants"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint(
            "compare_at_price IS NULL OR compare_at_price > price", name="compare_at_price"
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    # {"size": "42", "color": "white"}
    attributes: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, server_default=_jsonb_object()
    )
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # Old price shown crossed out (a discount).
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Set by the inventory module whenever stock changes.
    in_stock: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class ProductImage(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "product_images"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(_in("source", IMAGE_SOURCES), name="source"),
        CheckConstraint(_in("angle", IMAGE_ANGLES), name="angle"),
        CheckConstraint(_in("status", IMAGE_STATUSES), name="status"),
        CheckConstraint(_in("ai_check", AI_CHECKS), name="ai_check"),
        Index("ix_product_images_product_source", "product_id", "source", "status"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(8))
    angle: Mapped[str] = mapped_column(String(8), default="other")
    # Today a URL; with the media module it becomes an object-storage key.
    url: Mapped[str] = mapped_column(String(1000))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(10), default="approved")
    ai_check: Mapped[str] = mapped_column(
        String(12), default="unchecked", server_default="unchecked"
    )
