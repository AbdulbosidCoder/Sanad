"""Request and response bodies of the `cart` API."""

import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.modules.cart.models import MAX_QUANTITY

Quantity = Annotated[int, Field(ge=1, le=MAX_QUANTITY)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddItemIn(_In):
    variant_id: uuid.UUID
    quantity: Quantity = 1


class SetQuantityIn(_In):
    quantity: Quantity


class CartItemOut(BaseModel):
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_slug: str
    title: str
    sku: str
    attributes: dict[str, str]
    cover_url: str | None
    unit_price: Decimal
    compare_at_price: Decimal | None
    quantity: int
    line_total: Decimal
    available: int
    # null = OK; "unavailable" (removed from sale) or "not_enough_stock"
    problem: str | None = None


class StoreRef(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class CartGroupOut(BaseModel):
    """One seller's part of the cart: it becomes one seller order at checkout."""

    store: StoreRef
    items: list[CartItemOut]
    subtotal: Decimal


class CartOut(BaseModel):
    groups: list[CartGroupOut]
    item_count: int
    total: Decimal
    currency: str = "UZS"
    can_checkout: bool
