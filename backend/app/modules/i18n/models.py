"""Tables of the `i18n` module (docs/architecture/05-api-architecture.md, 5.5).

The seller writes a product in one language; the other two are translated by machine
(``origin = machine``). A seller's own edit (``manual``) is never overwritten: when the
original changes later, it is only flagged ``needs_review``. ``source_hash`` is the hash of
the original text a translation was made from.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

ORIGINS = ("machine", "manual")
JOB_STATUSES = ("pending", "done", "failed")


class ProductTranslation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "product_translations"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("product_id", "locale", name="uq_product_translations_locale"),
        CheckConstraint("locale IN ('uz', 'ru', 'en')", name="locale"),
        CheckConstraint("origin IN ('machine', 'manual')", name="origin"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    locale: Mapped[str] = mapped_column(String(2))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    origin: Mapped[str] = mapped_column(String(8))
    source_hash: Mapped[str] = mapped_column(String(64))
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class TranslationJob(UUIDPrimaryKey, Timestamps, Base):
    """Work for the background translator: one row per product and target language."""

    __tablename__ = "translation_jobs"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'done', 'failed')", name="status"),
        Index(
            "uq_translation_jobs_pending",
            "product_id",
            "locale",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_translation_jobs_status_created", "status", "created_at"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    locale: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(8), default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(500))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
