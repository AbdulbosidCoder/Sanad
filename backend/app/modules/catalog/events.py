"""Domain events of the `catalog` module.

Emits: ProductCreated, ProductUpdated, ProductArchived
Listens to: nothing
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductCreated:
    product_id: uuid.UUID
    store_id: uuid.UUID
    source_locale: str


@dataclass(frozen=True)
class ProductUpdated:
    """The text a buyer reads (title, description or its language) changed."""

    product_id: uuid.UUID
    store_id: uuid.UUID
    source_locale: str


@dataclass(frozen=True)
class ProductArchived:
    product_id: uuid.UUID
    store_id: uuid.UUID
