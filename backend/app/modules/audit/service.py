"""Business logic of the `audit` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

Other modules call ``record`` inside their own transaction, so the audit row is written
exactly when the action is (and rolled back with it).
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import uuid7
from app.modules.audit import repository as repo
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditOut, VerifyOut

GENESIS = "0" * 64
# What a finance employee (audit.read_finance) may see.
FINANCE_PREFIXES = ("payments.", "refunds.", "returns.", "orders.")


def _digest(prev: str, row: dict[str, Any]) -> str:
    body = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(f"{prev}|{body}".encode()).hexdigest()


def _content(entry: AuditLog) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "actor_id": str(entry.actor_id) if entry.actor_id else None,
        "action": entry.action,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "data": entry.data,
        "created_at": entry.created_at.astimezone(UTC).isoformat(),
    }


async def record(
    db: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    target_type: str,
    target_id: object,
    data: dict[str, Any] | None = None,
) -> None:
    """Appends one entry (no commit: it is part of the caller's transaction)."""
    await repo.lock_chain(db)
    prev = await repo.last_hash(db) or GENESIS
    entry = AuditLog(
        id=uuid7(),
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        data=json.loads(json.dumps(data or {}, default=str)),
        prev_hash=prev,
        created_at=datetime.now(UTC),
    )
    entry.hash = _digest(prev, _content(entry))
    db.add(entry)
    await db.flush()


async def search(
    db: AsyncSession,
    *,
    finance_only: bool,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    since: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
) -> list[AuditOut]:
    rows = await repo.search(
        db,
        actor_id=actor_id,
        action_prefixes=FINANCE_PREFIXES if finance_only else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        since=since,
        offset=offset,
        limit=limit,
    )
    return [AuditOut.model_validate(r) for r in rows]


async def verify(db: AsyncSession) -> VerifyOut:
    """Recomputes the whole chain."""
    prev, seq, checked = GENESIS, 0, 0
    while True:
        batch = await repo.chain(db, seq, 1000)
        if not batch:
            return VerifyOut(ok=True, checked=checked)
        for entry in batch:
            if entry.prev_hash != prev or entry.hash != _digest(prev, _content(entry)):
                return VerifyOut(ok=False, checked=checked, broken_at_seq=entry.seq)
            prev, seq, checked = entry.hash, entry.seq, checked + 1
