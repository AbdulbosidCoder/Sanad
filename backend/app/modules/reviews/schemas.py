"""Request and response bodies of the `reviews` API."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Fit = Literal["small", "true", "large"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)]


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    text: Text = ""
    fit: Fit | None = None


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int | None = Field(None, ge=1, le=5)
    text: Text | None = None
    fit: Fit | None = None


class ReplyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class HideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    rating: int
    text: str
    fit: Fit | None
    author: str  # first name and the initial of the last one
    verified_purchase: bool = True
    seller_reply: str | None
    replied_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModerationOut(ReviewOut):
    status: str
    hidden_reason: str | None
    user_id: uuid.UUID


class Summary(BaseModel):
    rating_avg: Decimal
    rating_count: int
    distribution: dict[int, int]  # stars -> reviews
    fit: dict[str, int]  # small / true / large -> reviews


class CanReview(BaseModel):
    can_review: bool
    reason: Literal["ok", "not_purchased", "already_reviewed", "sign_in"]
    review_id: uuid.UUID | None = None
