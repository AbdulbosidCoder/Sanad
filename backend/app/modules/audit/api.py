"""HTTP endpoints of the `audit` module. Business logic lives in service.py."""

import uuid
from datetime import datetime

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AUTH_MODULE, Principal, get_principal
from app.core.db import get_session
from app.core.errors import AppError
from app.core.modules import module_router
from app.core.pagination import decode_cursor
from app.modules.audit import service
from app.modules.audit.schemas import AuditOut, VerifyOut

router = module_router("audit")


def _scope(principal: Principal) -> bool:
    """True = finance part only. Raises 403 without any audit permission."""
    if "audit.read" in principal.permissions:
        return False
    if "audit.read_finance" in principal.permissions:
        return True
    raise AppError(AUTH_MODULE, "FORBIDDEN", "Not enough permissions", status=403)


@router.get("/admin/audit")
async def audit_log(
    actor_id: uuid.UUID | None = None,
    action: str | None = Query(None, max_length=64),
    target_type: str | None = Query(None, max_length=32),
    target_id: str | None = Query(None, max_length=64),
    since: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> list[AuditOut]:
    """Newest first. ``audit.read`` sees everything, ``audit.read_finance`` money actions."""
    return await service.search(
        db,
        finance_only=_scope(principal),
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        since=since,
        offset=decode_cursor(cursor, "audit"),
        limit=limit,
    )


@router.get("/admin/audit/verify")
async def verify(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> VerifyOut:
    """Checks that no entry was changed or removed (hash chain)."""
    if _scope(principal):
        raise AppError(AUTH_MODULE, "FORBIDDEN", "Not enough permissions", status=403)
    return await service.verify(db)
