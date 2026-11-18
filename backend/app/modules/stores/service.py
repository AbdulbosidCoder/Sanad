"""Business logic of the `stores` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

Seller requests name their store in the ``X-Store-Id`` header (docs 05-api-architecture.md).
``store_access(...)`` checks that the caller is a member of that store and that their
*store role* grants the permission. A store you are not a member of answers 404.
"""

import logging
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import Depends, Header
from sqlalchemy import Select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal
from app.core.db import get_session
from app.core.errors import AppError
from app.core.events import publish
from app.core.models import uuid7
from app.core.text import slugify
from app.modules.audit import service as audit
from app.modules.identity import service as identity
from app.modules.stores import repository as repo
from app.modules.stores.events import (
    SellerApplicationRejected,
    SellerApplicationSubmitted,
    StoreApproved,
    StoreSuspended,
)
from app.modules.stores.models import SellerApplication, Store, StoreMembership
from app.modules.stores.schemas import (
    ApplicationIn,
    ApplicationOut,
    MyStoreOut,
    StaffIn,
    StaffOut,
    StoreOut,
    StorePublicOut,
    StoreUpdate,
)

MODULE = "stores"
OWNER = "seller_owner"

logger = logging.getLogger("app.modules.stores")


def _error(code: str, detail: str, status: int) -> AppError:
    return AppError(MODULE, code, detail, status=status)


def _log(msg: str, **fields: object) -> None:
    logger.info(msg, extra={"extra_fields": {k: str(v) for k, v in fields.items()}})


def _not_found() -> AppError:
    return _error("STORE_NOT_FOUND", "Store not found", 404)


# ---------------------------------------------------------------- store access (for other modules)


@dataclass(frozen=True)
class StoreAccess:
    """The store a seller request works on, and what the caller may do there."""

    store_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    permissions: frozenset[str]
    store_active: bool

    def has(self, permission: str) -> bool:
        return permission in self.permissions


async def resolve_store_access(
    db: AsyncSession, principal: Principal, store_id: uuid.UUID | None
) -> StoreAccess:
    if store_id is None:
        stores = await repo.memberships_of(db, principal.user_id)
        if len(stores) != 1:
            raise _error(
                "STORE_REQUIRED",
                "Send X-Store-Id: you are a member of several stores (or of none)",
                400,
            )
        store, role = stores[0]
    else:
        membership = await repo.get_membership(db, store_id, principal.user_id)
        found = await repo.get_store(db, store_id) if membership else None
        if membership is None or found is None:
            raise _not_found()
        store, role = found, membership.role
    return StoreAccess(
        store.id,
        principal.user_id,
        role,
        identity.store_role_permissions(role),
        store.status == "active",
    )


def store_access(*permissions: str) -> Callable[..., Awaitable[StoreAccess]]:
    """FastAPI dependency for ``/seller/...`` endpoints.

    With permissions listed, the store must also be active: a suspended store can still
    be looked at by its staff, but nothing in it can be changed.
    """

    async def dependency(
        x_store_id: uuid.UUID | None = Header(None, description="Store to act on"),
        principal: Principal = Depends(get_principal),
        db: AsyncSession = Depends(get_session),
    ) -> StoreAccess:
        access = await resolve_store_access(db, principal, x_store_id)
        if any(not access.has(p) for p in permissions):
            raise _error("FORBIDDEN", "Your store role does not allow this", 403)
        if permissions and not access.store_active:
            raise _error("STORE_SUSPENDED", "The store is suspended", 403)
        return access

    return dependency


def active_store_ids() -> Select[Any]:
    """Subquery of stores whose goods may be shown to buyers."""
    return repo.active_store_ids()


@dataclass(frozen=True)
class StoreBrief:
    id: uuid.UUID
    slug: str
    name: str
    status: str


async def get_store_brief(db: AsyncSession, store_id: uuid.UUID) -> StoreBrief | None:
    store = await repo.get_store(db, store_id)
    return StoreBrief(store.id, store.slug, store.name, store.status) if store else None


async def find_store_id(db: AsyncSession, slug: str) -> uuid.UUID | None:
    store = await repo.get_store_by_slug(db, slug)
    return store.id if store else None


# ---------------------------------------------------------------- applications


async def apply(db: AsyncSession, principal: Principal, data: ApplicationIn) -> ApplicationOut:
    if await repo.has_open_application(db, principal.user_id):
        raise _error("APPLICATION_PENDING", "You already have an application under review", 409)
    application = SellerApplication(
        id=uuid7(),
        user_id=principal.user_id,
        store_name=data.store_name,
        description=data.description,
        phone=data.phone,
        documents=data.documents,
    )
    db.add(application)
    try:
        await db.flush()
        await publish(
            db, SellerApplicationSubmitted(application.id, principal.user_id, data.store_name)
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(
            "APPLICATION_PENDING", "You already have an application under review", 409
        ) from exc
    _log("seller application submitted", application_id=application.id)
    return ApplicationOut.model_validate(application)


async def my_applications(db: AsyncSession, principal: Principal) -> list[ApplicationOut]:
    return [
        ApplicationOut.model_validate(a) for a in await repo.applications_of(db, principal.user_id)
    ]


async def list_applications(
    db: AsyncSession, status: str | None, offset: int, limit: int
) -> list[ApplicationOut]:
    rows = await repo.list_applications(db, status, offset, limit)
    return [ApplicationOut.model_validate(a) for a in rows]


async def _free_slug(db: AsyncSession, name: str) -> str:
    base = slugify(name, 70)
    slug = base
    while await repo.slug_taken(db, slug):
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


async def create_store(
    db: AsyncSession,
    owner_id: uuid.UUID,
    name: str,
    *,
    description: str = "",
    phone: str | None = None,
    logo_url: str | None = None,
) -> Store:
    """Creates an active store with ``owner_id`` as its owner. Flushes, the caller commits."""
    store = Store(
        id=uuid7(),
        owner_id=owner_id,
        slug=await _free_slug(db, name),
        name=name,
        description=description,
        phone=phone,
        logo_url=logo_url,
    )
    db.add(store)
    await db.flush()
    db.add(StoreMembership(store_id=store.id, user_id=owner_id, role=OWNER))
    await db.flush()
    return store


async def _open_application(db: AsyncSession, app_id: uuid.UUID) -> SellerApplication:
    application = await repo.lock_application(db, app_id)
    if application is None:
        raise _error("APPLICATION_NOT_FOUND", "Application not found", 404)
    if application.status != "submitted":
        raise _error("APPLICATION_DECIDED", "The application is already decided", 409)
    return application


async def approve(
    db: AsyncSession, reviewer: Principal, app_id: uuid.UUID, note: str | None
) -> ApplicationOut:
    """Creates the store and makes the applicant its owner."""
    application = await _open_application(db, app_id)
    store = await create_store(
        db,
        application.user_id,
        application.store_name,
        description=application.description,
        phone=application.phone,
    )
    application.status = "approved"
    application.store_id = store.id
    application.review_note = note
    application.reviewed_by = reviewer.user_id
    application.reviewed_at = datetime.now(UTC)
    await publish(db, StoreApproved(store.id, application.user_id, store.name))
    await audit.record(
        db, reviewer.user_id, "stores.approve", "seller_application", app_id, {"store_id": store.id}
    )
    await db.commit()
    _log(
        "seller application approved",
        application_id=app_id,
        store_id=store.id,
        reviewer=reviewer.user_id,
    )
    return ApplicationOut.model_validate(application)


async def reject(
    db: AsyncSession, reviewer: Principal, app_id: uuid.UUID, note: str | None
) -> ApplicationOut:
    application = await _open_application(db, app_id)
    application.status = "rejected"
    application.review_note = note
    application.reviewed_by = reviewer.user_id
    application.reviewed_at = datetime.now(UTC)
    await publish(
        db,
        SellerApplicationRejected(
            application.id, application.user_id, application.store_name, note
        ),
    )
    await audit.record(
        db, reviewer.user_id, "stores.reject", "seller_application", app_id, {"note": note}
    )
    await db.commit()
    _log("seller application rejected", application_id=app_id, reviewer=reviewer.user_id)
    return ApplicationOut.model_validate(application)


# ---------------------------------------------------------------- stores


async def public_store(db: AsyncSession, slug: str) -> StorePublicOut:
    store = await repo.get_store_by_slug(db, slug)
    if store is None or store.status != "active":
        raise _not_found()
    return StorePublicOut.model_validate(store)


async def my_stores(db: AsyncSession, principal: Principal) -> list[MyStoreOut]:
    return [
        MyStoreOut(
            store=StoreOut.model_validate(store),
            role=role,
            permissions=sorted(identity.store_role_permissions(role)),
        )
        for store, role in await repo.memberships_of(db, principal.user_id)
    ]


async def _store(db: AsyncSession, store_id: uuid.UUID) -> Store:
    store = await repo.get_store(db, store_id)
    if store is None:
        raise _not_found()
    return store


async def get_store(db: AsyncSession, store_id: uuid.UUID) -> StoreOut:
    return StoreOut.model_validate(await _store(db, store_id))


async def update_store(db: AsyncSession, access: StoreAccess, data: StoreUpdate) -> StoreOut:
    store = await _store(db, access.store_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field == "name":
            continue
        setattr(store, field, value)
    await db.commit()
    return StoreOut.model_validate(store)


async def list_stores(
    db: AsyncSession, status: str | None, offset: int, limit: int
) -> list[StoreOut]:
    return [StoreOut.model_validate(s) for s in await repo.list_stores(db, status, offset, limit)]


async def suspend(db: AsyncSession, actor: Principal, store_id: uuid.UUID, reason: str) -> StoreOut:
    store = await _store(db, store_id)
    store.status = "suspended"
    store.suspended_reason = reason
    await publish(db, StoreSuspended(store.id, store.name, reason))
    await audit.record(db, actor.user_id, "stores.suspend", "store", store_id, {"reason": reason})
    await db.commit()
    _log("store suspended", store_id=store_id, actor=actor.user_id)
    return StoreOut.model_validate(store)


async def reactivate(db: AsyncSession, actor: Principal, store_id: uuid.UUID) -> StoreOut:
    store = await _store(db, store_id)
    store.status = "active"
    store.suspended_reason = None
    await audit.record(db, actor.user_id, "stores.reactivate", "store", store_id)
    await db.commit()
    _log("store reactivated", store_id=store_id, actor=actor.user_id)
    return StoreOut.model_validate(store)


# ---------------------------------------------------------------- staff


async def list_staff(db: AsyncSession, access: StoreAccess) -> list[StaffOut]:
    out: list[StaffOut] = []
    for m in await repo.staff_of(db, access.store_id):
        brief = await identity.user_brief(db, m.user_id)
        email, name = brief or (None, "")
        out.append(
            StaffOut(
                user_id=m.user_id, email=email, full_name=name, role=m.role, created_at=m.created_at
            )
        )
    return out


async def add_staff(db: AsyncSession, access: StoreAccess, data: StaffIn) -> list[StaffOut]:
    user_id = await identity.find_user_id(db, data.login)
    if user_id is None:
        raise _error("USER_NOT_FOUND", "No account with this email or phone", 404)
    existing = await repo.get_membership(db, access.store_id, user_id)
    if existing is not None:
        if existing.role == OWNER:
            raise _error("OWNER_ROLE", "The owner's role cannot be changed", 409)
        existing.role = data.role
    else:
        db.add(StoreMembership(store_id=access.store_id, user_id=user_id, role=data.role))
    await db.commit()
    _log("store staff set", store_id=access.store_id, user_id=user_id, role=data.role)
    return await list_staff(db, access)


async def remove_staff(db: AsyncSession, access: StoreAccess, user_id: uuid.UUID) -> None:
    membership = await repo.get_membership(db, access.store_id, user_id)
    if membership is None:
        raise _error("STAFF_NOT_FOUND", "Not a member of this store", 404)
    if membership.role == OWNER:
        raise _error("OWNER_ROLE", "The owner cannot be removed", 409)
    await db.delete(membership)
    await db.commit()
    _log("store staff removed", store_id=access.store_id, user_id=user_id)


async def commission_rate(db: AsyncSession, store_id: uuid.UUID) -> Decimal:
    """The store's current platform commission (a fraction: 0.1 = 10 %)."""
    return (await _store(db, store_id)).commission_rate


async def staff_with_permission(
    db: AsyncSession, store_id: uuid.UUID, permission: str
) -> list[uuid.UUID]:
    """Users of a store whose role grants ``permission`` (who to notify about what)."""
    return [
        m.user_id
        for m in await repo.staff_of(db, store_id)
        if permission in identity.store_role_permissions(m.role)
    ]
