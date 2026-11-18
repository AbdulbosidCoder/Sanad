"""Tables of the `support` module: tickets and their messages.

Statuses: ``open`` (waiting for support) -> ``answered`` (waiting for the customer) ->
``resolved`` (support thinks it is done; a new customer message reopens it) -> ``closed``.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

TICKET_STATUSES = ("open", "answered", "resolved", "closed")
CATEGORIES = ("order", "payment", "return", "product", "account", "seller", "other")
PRIORITIES = ("low", "normal", "high", "urgent")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class SupportTicket(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "support_tickets"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(_in("status", TICKET_STATUSES), name="status"),
        CheckConstraint(_in("category", CATEGORIES), name="category"),
        CheckConstraint(_in("priority", PRIORITIES), name="priority"),
        Index("ix_support_tickets_user_created", "user_id", "created_at"),
        Index("ix_support_tickets_status_activity", "status", "last_activity_at"),
        Index("ix_support_tickets_assignee_status", "assignee_id", "status"),
    )

    number: Mapped[str] = mapped_column(String(16), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    subject: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(10))
    priority: Mapped[str] = mapped_column(String(8), default="normal", server_default="normal")
    status: Mapped[str] = mapped_column(String(10), default="open", server_default="open")
    order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    order_number: Mapped[str | None] = mapped_column(String(20))
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportMessage(UUIDPrimaryKey, Base):
    __tablename__ = "support_messages"
    __table_args__ = (Index("ix_support_messages_ticket_created", "ticket_id", "created_at"),)

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE")
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    from_staff: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    internal: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
