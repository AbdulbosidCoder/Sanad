"""Table of the `audit` module.

``audit_logs`` is append-only: the migration installs a trigger that rejects UPDATE and
DELETE. Every row stores the SHA-256 of the previous row (``prev_hash``) and its own
(``hash``), so a row changed directly in the database breaks the chain and
``GET /admin/audit/verify`` shows where.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import UUIDPrimaryKey


class AuditLog(UUIDPrimaryKey, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
        Index("ix_audit_logs_target", "target_type", "target_id"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # None = system
    action: Mapped[str] = mapped_column(String(64))  # e.g. users.block, refunds.approve
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
