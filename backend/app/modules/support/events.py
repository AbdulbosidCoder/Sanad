"""Domain events of the `support` module.

Emits: TicketCreated, TicketReplied (staff answered the customer; internal notes do not count)
Listens to: nothing
"""

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class TicketCreated:
    ticket_id: uuid.UUID
    user_id: uuid.UUID
    number: str
    category: str


@dataclass(frozen=True)
class TicketReplied:
    ticket_id: uuid.UUID
    user_id: uuid.UUID  # the customer
    number: str
    subject: str
