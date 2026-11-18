"""Domain events of the `engagement` module.

Emits: ProductViewed (a product page was opened; counted once per viewer per 30 minutes)
Listens to: nothing
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductViewed:
    product_id: uuid.UUID
    store_id: uuid.UUID
    user_id: uuid.UUID | None
