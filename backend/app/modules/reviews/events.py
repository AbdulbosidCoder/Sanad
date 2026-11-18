"""Domain events of the `reviews` module.

Emits: ReviewPublished (a buyer published or edited a review)
Listens to: nothing
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewPublished:
    review_id: uuid.UUID
    product_id: uuid.UUID
    store_id: uuid.UUID
    rating: int
