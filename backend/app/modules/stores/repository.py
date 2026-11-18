"""Database queries of the `stores` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.stores.models import SellerApplication, Store, StoreMembership


async def get_store(db: AsyncSession, store_id: uuid.UUID) -> Store | None:
    return await db.get(Store, store_id)


async def get_store_by_slug(db: AsyncSession, slug: str) -> Store | None:
    return await db.scalar(select(Store).where(Store.slug == slug))


async def slug_taken(db: AsyncSession, slug: str) -> bool:
    return bool(await db.scalar(select(func.count()).where(Store.slug == slug)))


async def list_stores(
    db: AsyncSession, status: str | None, offset: int, limit: int
) -> Sequence[Store]:
    stmt = select(Store).order_by(Store.created_at.desc(), Store.id)
    if status:
        stmt = stmt.where(Store.status == status)
    return (await db.scalars(stmt.offset(offset).limit(limit))).all()


async def get_membership(
    db: AsyncSession, store_id: uuid.UUID, user_id: uuid.UUID
) -> StoreMembership | None:
    return await db.get(StoreMembership, (store_id, user_id))


async def memberships_of(db: AsyncSession, user_id: uuid.UUID) -> Sequence[tuple[Store, str]]:
    rows = await db.execute(
        select(Store, StoreMembership.role)
        .join(StoreMembership, StoreMembership.store_id == Store.id)
        .where(StoreMembership.user_id == user_id)
        .order_by(Store.created_at)
    )
    return [(store, role) for store, role in rows.all()]


async def staff_of(db: AsyncSession, store_id: uuid.UUID) -> Sequence[StoreMembership]:
    return (
        await db.scalars(
            select(StoreMembership)
            .where(StoreMembership.store_id == store_id)
            .order_by(StoreMembership.created_at)
        )
    ).all()


async def get_application(db: AsyncSession, app_id: uuid.UUID) -> SellerApplication | None:
    return await db.get(SellerApplication, app_id)


async def lock_application(db: AsyncSession, app_id: uuid.UUID) -> SellerApplication | None:
    return await db.scalar(
        select(SellerApplication).where(SellerApplication.id == app_id).with_for_update()
    )


async def applications_of(db: AsyncSession, user_id: uuid.UUID) -> Sequence[SellerApplication]:
    return (
        await db.scalars(
            select(SellerApplication)
            .where(SellerApplication.user_id == user_id)
            .order_by(SellerApplication.created_at.desc())
        )
    ).all()


async def has_open_application(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return bool(
        await db.scalar(
            select(func.count()).where(
                SellerApplication.user_id == user_id, SellerApplication.status == "submitted"
            )
        )
    )


async def list_applications(
    db: AsyncSession, status: str | None, offset: int, limit: int
) -> Sequence[SellerApplication]:
    stmt = select(SellerApplication).order_by(SellerApplication.created_at, SellerApplication.id)
    if status:
        stmt = stmt.where(SellerApplication.status == status)
    return (await db.scalars(stmt.offset(offset).limit(limit))).all()


def active_store_ids() -> Select[Any]:
    return select(Store.id).where(Store.status == "active")
