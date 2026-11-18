"""Response bodies of the `audit` API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    seq: int
    actor_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: str
    data: dict[str, Any]
    hash: str
    created_at: datetime


class VerifyOut(BaseModel):
    ok: bool
    checked: int
    broken_at_seq: int | None = None
