"""Domain events of the `stores` module.

Emits: SellerApplicationSubmitted, StoreApproved, SellerApplicationRejected, StoreSuspended
Listens to: nothing
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class SellerApplicationSubmitted:
    application_id: uuid.UUID
    user_id: uuid.UUID
    store_name: str


@dataclass(frozen=True)
class StoreApproved:
    store_id: uuid.UUID
    owner_id: uuid.UUID
    name: str


@dataclass(frozen=True)
class SellerApplicationRejected:
    application_id: uuid.UUID
    user_id: uuid.UUID
    store_name: str
    note: str | None


@dataclass(frozen=True)
class StoreSuspended:
    store_id: uuid.UUID
    name: str
    reason: str
