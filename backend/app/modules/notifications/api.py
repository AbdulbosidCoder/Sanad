"""HTTP endpoints of the `notifications` module. Business logic lives in service.py."""

import uuid

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.db import get_session
from app.core.modules import module_router
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, decode_cursor
from app.modules.notifications import service
from app.modules.notifications.schemas import (
    NotificationOut,
    PreferencesIn,
    PreferencesOut,
    UnreadOut,
)

router = module_router("notifications")


@router.get("/me/notifications")
async def inbox(
    unread_only: bool = False,
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> Page[NotificationOut]:
    return await service.inbox(
        db, principal, unread_only, decode_cursor(cursor, "notifications"), limit
    )


@router.get("/me/notifications/unread-count")
async def unread(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> UnreadOut:
    """The number on the bell."""
    return await service.unread(db, principal)


@router.post("/me/notifications/{notification_id}/read")
async def read_one(
    notification_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> UnreadOut:
    return await service.mark_read(db, principal, notification_id)


@router.post("/me/notifications/read-all")
async def read_all(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> UnreadOut:
    return await service.mark_read(db, principal, None)


@router.get("/me/notification-preferences")
async def preferences(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> PreferencesOut:
    return await service.get_preferences(db, principal)


@router.patch("/me/notification-preferences")
async def update_preferences(
    data: PreferencesIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> PreferencesOut:
    return await service.update_preferences(db, principal, data)
