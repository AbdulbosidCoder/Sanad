"""Domain events of the `i18n` module.

Emits: TranslationReady (a product's text in one language was written or changed)
Listens to: ProductCreated, ProductUpdated
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class TranslationReady:
    product_id: uuid.UUID
    locale: str
