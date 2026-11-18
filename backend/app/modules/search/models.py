"""Tables of the `search` module.

``search_documents``: one row per product with all its searchable text (original, every
translation, brand, category names) lower-cased in ``document``. ``tsv`` is a generated
full-text vector of it (GIN index); a trigram index on ``document`` catches typos.
``search_history``: what a signed-in buyer searched, one row per distinct query.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Computed, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey


class SearchDocument(Base):
    __tablename__ = "search_documents"
    __table_args__ = (
        Index("ix_search_documents_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_search_documents_trgm",
            "document",
            postgresql_using="gin",
            postgresql_ops={"document": "gin_trgm_ops"},
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    document: Mapped[str] = mapped_column(Text)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', document)", persisted=True)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SearchHistory(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "search_history"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        UniqueConstraint("user_id", "query", name="uq_search_history_query"),
        Index("ix_search_history_user_searched", "user_id", "searched_at"),
        Index("ix_search_history_searched", "searched_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    query: Mapped[str] = mapped_column(String(100))
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
