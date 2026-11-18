"""Cursor pagination for lists (``?cursor=&limit=``).

The cursor is opaque to clients: today it encodes an offset, so the storage behind it can
switch to keyset pagination later without changing the API.
"""

import base64
import binascii

from pydantic import BaseModel

from app.core.errors import AppError

DEFAULT_LIMIT = 20
MAX_LIMIT = 50


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


def decode_cursor(cursor: str | None, module: str) -> int:
    if not cursor:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise AppError(module, "BAD_CURSOR", "Invalid cursor", status=400) from exc
    if offset < 0:
        raise AppError(module, "BAD_CURSOR", "Invalid cursor", status=400)
    return offset


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def next_cursor(offset: int, limit: int, fetched: int) -> str | None:
    """Call with ``fetched`` = rows returned by a query that asked for ``limit + 1``."""
    return encode_cursor(offset + limit) if fetched > limit else None
