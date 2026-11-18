"""Request and response bodies of the `notifications` API."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str | None
    data: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class UnreadOut(BaseModel):
    unread: int


class PreferencesOut(BaseModel):
    email_enabled: bool
    muted_kinds: list[str]
    kinds: list[str]  # every kind that exists, for the settings screen


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_enabled: bool | None = None
    muted_kinds: list[str] | None = None
