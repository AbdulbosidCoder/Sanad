"""Tables of the `notifications` module.

``notifications`` is the in-app inbox (the bell). ``email_outbox`` holds e-mails to send:
they are written in the same transaction as the event that caused them and sent by the
worker afterwards, so a failing mail server never breaks an order.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey


def _user_fk() -> ForeignKey:
    return ForeignKey("users.id", ondelete="CASCADE")


class Notification(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "notifications"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _user_fk())
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    link: Mapped[str | None] = mapped_column(String(300))  # path in the app, e.g. /orders/...
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreference(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "notification_preferences"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _user_fk(), unique=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    muted_kinds: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")


class EmailOutbox(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "email_outbox"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sent', 'failed')", name="status"),
        Index("ix_email_outbox_status_created", "status", "created_at"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    to_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(8), default="pending", server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(500))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
