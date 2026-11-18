"""Request and response bodies of the `engagement` API."""

import uuid

from pydantic import BaseModel


class FavoriteState(BaseModel):
    product_id: uuid.UUID
    favorite: bool


class ViewOut(BaseModel):
    counted: bool  # False when the same viewer opened the product in the last 30 minutes
