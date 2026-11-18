"""Request and response bodies of the `support` API."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Category = Literal["order", "payment", "return", "product", "account", "seller", "other"]
Priority = Literal["low", "normal", "high", "urgent"]
Status = Literal["open", "answered", "resolved", "closed"]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TicketIn(_In):
    subject: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
    category: Category
    message: Body
    order_id: uuid.UUID | None = None


class MessageIn(_In):
    body: Body


class StaffMessageIn(MessageIn):
    internal: bool = False  # a note for colleagues, invisible to the customer


class TicketUpdate(_In):
    status: Status | None = None
    priority: Priority | None = None


class AssignIn(_In):
    assignee_id: uuid.UUID | None  # None = back to the queue


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_staff: bool
    internal: bool
    body: str
    created_at: datetime


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    subject: str
    category: Category
    priority: Priority
    status: Status
    order_id: uuid.UUID | None
    order_number: str | None
    created_at: datetime
    last_activity_at: datetime


class StaffTicketOut(TicketOut):
    user_id: uuid.UUID
    assignee_id: uuid.UUID | None


class TicketDetail(TicketOut):
    messages: list[MessageOut]


class StaffTicketDetail(StaffTicketOut):
    messages: list[MessageOut]
    customer_email: str | None
    customer_name: str
