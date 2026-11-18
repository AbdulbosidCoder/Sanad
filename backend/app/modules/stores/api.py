"""HTTP endpoints of the `stores` module. Business logic lives in service.py."""

import uuid
from typing import Literal

from fastapi import Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_permission, require_sensitive_action
from app.core.db import get_session
from app.core.modules import module_router
from app.core.ratelimit import rate_limit
from app.modules.stores import service
from app.modules.stores.schemas import (
    ApplicationIn,
    ApplicationOut,
    MyStoreOut,
    ReviewIn,
    StaffIn,
    StaffOut,
    StoreOut,
    StorePublicOut,
    StoreUpdate,
    SuspendIn,
)
from app.modules.stores.service import StoreAccess, store_access

router = module_router("stores")

ApplicationStatus = Literal["submitted", "approved", "rejected"]
StoreStatus = Literal["active", "suspended"]
Offset = Query(0, ge=0)
Limit = Query(50, ge=1, le=200)


# ---------------------------------------------------------------- public


@router.get("/stores/{slug}")
async def public_store(slug: str, db: AsyncSession = Depends(get_session)) -> StorePublicOut:
    """Store page header. Its goods: ``GET /products?store=<slug>``."""
    return await service.public_store(db, slug)


# ---------------------------------------------------------------- seller


@router.post(
    "/seller/applications",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("stores.apply", 5, 86400))],
)
async def apply(
    data: ApplicationIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> ApplicationOut:
    """Any signed-in user may ask to open a store; an admin approves it."""
    return await service.apply(db, principal, data)


@router.get("/seller/applications")
async def my_applications(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> list[ApplicationOut]:
    return await service.my_applications(db, principal)


@router.get("/seller/stores")
async def my_stores(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> list[MyStoreOut]:
    """Stores the caller works in, with their role. Pick one and send it as ``X-Store-Id``."""
    return await service.my_stores(db, principal)


@router.get("/seller/store")
async def get_my_store(
    access: StoreAccess = Depends(store_access()), db: AsyncSession = Depends(get_session)
) -> StoreOut:
    return await service.get_store(db, access.store_id)


@router.patch("/seller/store")
async def update_my_store(
    data: StoreUpdate,
    access: StoreAccess = Depends(store_access("store.settings_manage")),
    db: AsyncSession = Depends(get_session),
) -> StoreOut:
    return await service.update_store(db, access, data)


@router.get("/seller/staff")
async def list_staff(
    access: StoreAccess = Depends(store_access("store.staff_manage")),
    db: AsyncSession = Depends(get_session),
) -> list[StaffOut]:
    return await service.list_staff(db, access)


@router.post("/seller/staff")
async def add_staff(
    data: StaffIn,
    access: StoreAccess = Depends(store_access("store.staff_manage")),
    db: AsyncSession = Depends(get_session),
) -> list[StaffOut]:
    """Adds a registered user to the store, or changes their role."""
    return await service.add_staff(db, access, data)


@router.delete("/seller/staff/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_staff(
    user_id: uuid.UUID,
    access: StoreAccess = Depends(store_access("store.staff_manage")),
    db: AsyncSession = Depends(get_session),
) -> None:
    await service.remove_staff(db, access, user_id)


# ---------------------------------------------------------------- admin


@router.get("/admin/seller-applications")
async def list_applications(
    status_: ApplicationStatus | None = Query(None, alias="status"),
    offset: int = Offset,
    limit: int = Limit,
    _: Principal = Depends(require_permission("seller_applications.review")),
    db: AsyncSession = Depends(get_session),
) -> list[ApplicationOut]:
    return await service.list_applications(db, status_, offset, limit)


@router.post("/admin/seller-applications/{app_id}/approve")
async def approve(
    app_id: uuid.UUID,
    data: ReviewIn | None = None,
    principal: Principal = Depends(require_sensitive_action("seller_applications.review")),
    db: AsyncSession = Depends(get_session),
) -> ApplicationOut:
    return await service.approve(db, principal, app_id, data.note if data else None)


@router.post("/admin/seller-applications/{app_id}/reject")
async def reject(
    app_id: uuid.UUID,
    data: ReviewIn | None = None,
    principal: Principal = Depends(require_sensitive_action("seller_applications.review")),
    db: AsyncSession = Depends(get_session),
) -> ApplicationOut:
    return await service.reject(db, principal, app_id, data.note if data else None)


@router.get("/admin/stores")
async def list_stores(
    status_: StoreStatus | None = Query(None, alias="status"),
    offset: int = Offset,
    limit: int = Limit,
    _: Principal = Depends(require_permission("stores.suspend")),
    db: AsyncSession = Depends(get_session),
) -> list[StoreOut]:
    return await service.list_stores(db, status_, offset, limit)


@router.post("/admin/stores/{store_id}/suspend")
async def suspend(
    store_id: uuid.UUID,
    data: SuspendIn,
    principal: Principal = Depends(require_sensitive_action("stores.suspend")),
    db: AsyncSession = Depends(get_session),
) -> StoreOut:
    """Hides the store's goods from buyers and freezes changes in it."""
    return await service.suspend(db, principal, store_id, data.reason)


@router.post("/admin/stores/{store_id}/reactivate")
async def reactivate(
    store_id: uuid.UUID,
    principal: Principal = Depends(require_sensitive_action("stores.suspend")),
    db: AsyncSession = Depends(get_session),
) -> StoreOut:
    return await service.reactivate(db, principal, store_id)
