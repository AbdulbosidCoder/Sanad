"""In-process domain events.

A module publishes an event (a frozen dataclass from its ``events.py``); modules that
declared it in ``listens_to`` subscribe a handler in their ``setup`` hook. Handlers run
*in the publisher's transaction*: either everything (payment + order + stock) is saved, or
nothing is. Later, handlers that may be slow move to the worker through an outbox table;
publishers do not change.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("app.core.events")

Handler = Callable[[AsyncSession, Any], Awaitable[None]]

_handlers: dict[type, list[Handler]] = {}


def subscribe(event_type: type, handler: Handler) -> None:
    """Idempotent: subscribing the same handler twice keeps one."""
    handlers = _handlers.setdefault(event_type, [])
    if handler not in handlers:
        handlers.append(handler)


async def publish(db: AsyncSession, event: object) -> None:
    logger.info("event %s", type(event).__name__, extra={"extra_fields": {"event": repr(event)}})
    for handler in _handlers.get(type(event), []):
        await handler(db, event)
