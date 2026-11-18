"""Domain events of the `inventory` module.

Emits: StockLow (a sale took free stock down to the variant's threshold or below)
Listens to: nothing (orders calls reserve / commit / release directly)
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class StockLow:
    store_id: uuid.UUID
    variant_id: uuid.UUID
    sku: str
    title: str
    available: int
    threshold: int
