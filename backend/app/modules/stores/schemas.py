"""Request and response bodies of the `stores` API. Input models forbid unknown fields."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.modules.identity.service import normalize_phone

Phone = Annotated[str, AfterValidator(normalize_phone)]
StoreName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Url = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^https?://", max_length=1000)
]
StaffRole = Literal["seller_manager", "seller_staff"]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ApplicationIn(_In):
    store_name: StoreName
    description: Description = ""
    phone: Phone
    documents: dict[str, Any] = Field(
        default_factory=dict, description="Registration data (INN, licence links); free form"
    )


class ApplicationOut(_Out):
    id: uuid.UUID
    user_id: uuid.UUID
    store_name: str
    description: str
    phone: str
    status: str
    review_note: str | None
    reviewed_at: datetime | None
    store_id: uuid.UUID | None
    created_at: datetime


class ReviewIn(_In):
    note: Note | None = None


class StorePublicOut(_Out):
    id: uuid.UUID
    slug: str
    name: str
    description: str
    logo_url: str | None
    created_at: datetime


class StoreOut(StorePublicOut):
    owner_id: uuid.UUID
    phone: str | None
    status: str
    commission_rate: Decimal
    suspended_reason: str | None


class MyStoreOut(BaseModel):
    store: StoreOut
    role: str
    permissions: list[str]


class StoreUpdate(_In):
    name: StoreName | None = None
    description: Description | None = None
    logo_url: Url | None = None
    phone: Phone | None = None


class SuspendIn(_In):
    reason: Note


class StaffIn(_In):
    login: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
    role: StaffRole


class StaffOut(BaseModel):
    user_id: uuid.UUID
    email: str | None
    full_name: str
    role: str
    created_at: datetime
