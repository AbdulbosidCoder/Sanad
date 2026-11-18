"""Request and response bodies of the `inventory` API."""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Count = Annotated[int, Field(ge=0, le=1_000_000)]


class StockUpdate(BaseModel):
    """Either set the count (``on_hand``) or change it (``delta``: +10 arrived, -2 damaged)."""

    model_config = ConfigDict(extra="forbid")

    on_hand: Count | None = None
    delta: Annotated[int, Field(ge=-1_000_000, le=1_000_000)] | None = None
    low_stock_threshold: Count | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None

    @model_validator(mode="after")
    def _one_way(self) -> Self:
        if self.on_hand is not None and self.delta is not None:
            raise ValueError("send on_hand or delta, not both")
        if self.on_hand is None and self.delta is None and self.low_stock_threshold is None:
            raise ValueError("nothing to change")
        return self


class StockOut(BaseModel):
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_title: str
    product_status: str
    sku: str
    attributes: dict[str, str]
    on_hand: int
    reserved: int
    available: int
    low_stock_threshold: int
    low_stock: bool


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    delta: int
    on_hand_after: int
    reason: str
    note: str | None
    actor_id: uuid.UUID | None
    created_at: datetime
