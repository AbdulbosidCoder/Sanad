"""Shared column conventions for every table (docs/architecture/03-database-er.md).

- Primary keys are UUID v7: time-sortable (good for B-tree indexes) and safe to expose.
- Every table has ``created_at`` / ``updated_at`` (timestamptz, set by the database).
"""

import os
import time
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def uuid7() -> uuid.UUID:
    """RFC 9562 UUID version 7 (48-bit ms timestamp + random). Python < 3.14 has no uuid7()."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ms & ((1 << 48) - 1)) << 80
    value |= 0x7 << 76  # version
    value |= ((rand >> 62) & 0xFFF) << 64  # rand_a, 12 bits
    value |= 0b10 << 62  # variant
    value |= rand & ((1 << 62) - 1)  # rand_b, 62 bits
    return uuid.UUID(int=value)


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
