"""Domain events of the `search` module.

Emits: SearchPerformed (a buyer searched; analytics counts queries)
Listens to: ProductCreated, ProductUpdated, ProductArchived, TranslationReady (reindex)
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class SearchPerformed:
    query: str
    user_id: uuid.UUID | None
    results: int  # cards on the first page
