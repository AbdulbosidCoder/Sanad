"""Database queries of the `identity` module. No business rules here, only data access."""

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import uuid7
from app.modules.identity.models import (
    Address,
    AuthSession,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    User,
    UserCredential,
    UserRole,
)

# ---------------------------------------------------------------- users


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))


async def find_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))


async def find_user_by_phone(db: AsyncSession, phone: str) -> User | None:
    return await db.scalar(select(User).where(User.phone == phone, User.deleted_at.is_(None)))


async def email_exists(db: AsyncSession, email: str) -> bool:
    return bool(await db.scalar(select(func.count()).where(User.email == email)))


async def phone_exists(db: AsyncSession, phone: str) -> bool:
    return bool(await db.scalar(select(func.count()).where(User.phone == phone)))


async def get_password_credential(db: AsyncSession, user_id: uuid.UUID) -> UserCredential | None:
    return await db.scalar(
        select(UserCredential).where(
            UserCredential.user_id == user_id, UserCredential.type == "password"
        )
    )


# ---------------------------------------------------------------- roles and permissions


async def get_role_by_code(db: AsyncSession, code: str) -> Role | None:
    return await db.scalar(select(Role).where(Role.code == code))


async def add_user_role(
    db: AsyncSession, user_id: uuid.UUID, role_id: uuid.UUID, granted_by: uuid.UUID | None = None
) -> None:
    await db.execute(
        insert(UserRole)
        .values(user_id=user_id, role_id=role_id, granted_by=granted_by)
        .on_conflict_do_nothing()
    )


async def platform_roles_and_permissions(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[frozenset[str], frozenset[str]]:
    rows = (
        await db.execute(
            select(Role.code, Permission.code)
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .outerjoin(RolePermission, RolePermission.role_id == Role.id)
            .outerjoin(Permission, Permission.id == RolePermission.permission_id)
            .where(UserRole.user_id == user_id, Role.scope == "platform")
        )
    ).all()
    roles = frozenset(r for r, _ in rows)
    permissions = frozenset(p for _, p in rows if p is not None)
    return roles, permissions


async def upsert_permissions(db: AsyncSession, items: dict[str, str]) -> dict[str, uuid.UUID]:
    # Core INSERTs skip ORM defaults, so ids are generated here.
    stmt = insert(Permission).values(
        [{"id": uuid7(), "code": c, "description": d} for c, d in items.items()]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[Permission.code], set_={"description": stmt.excluded.description}
    )
    await db.execute(stmt)
    rows = await db.execute(select(Permission.code, Permission.id))
    return {code: pid for code, pid in rows.all()}


async def upsert_role(db: AsyncSession, code: str, scope: str, description: str) -> uuid.UUID:
    stmt = (
        insert(Role)
        .values(id=uuid7(), code=code, scope=scope, description=description, is_system=True)
        .on_conflict_do_update(
            index_elements=[Role.code],
            set_={"scope": scope, "description": description, "is_system": True},
        )
        .returning(Role.id)
    )
    role_id: uuid.UUID = (await db.execute(stmt)).scalar_one()
    return role_id


async def set_role_permissions(
    db: AsyncSession, role_id: uuid.UUID, permission_ids: Iterable[uuid.UUID]
) -> None:
    wanted = list(permission_ids)
    await db.execute(
        delete(RolePermission).where(
            RolePermission.role_id == role_id, RolePermission.permission_id.not_in(wanted)
        )
    )
    if wanted:
        await db.execute(
            insert(RolePermission)
            .values([{"role_id": role_id, "permission_id": p} for p in wanted])
            .on_conflict_do_nothing()
        )


# ---------------------------------------------------------------- sessions and refresh tokens


async def get_live_session(
    db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID, now: datetime
) -> AuthSession | None:
    """Session that may be used right now: not revoked, not expired, owner active."""
    return await db.scalar(
        select(AuthSession)
        .join(User, User.id == AuthSession.user_id)
        .where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
            User.status == "active",
            User.deleted_at.is_(None),
        )
    )


async def list_live_sessions(
    db: AsyncSession, user_id: uuid.UUID, now: datetime
) -> Sequence[AuthSession]:
    return (
        await db.scalars(
            select(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
            .order_by(AuthSession.last_seen_at.desc())
        )
    ).all()


async def revoke_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    now: datetime,
    reason: str,
    *,
    only: uuid.UUID | None = None,
    keep: uuid.UUID | None = None,
) -> int:
    stmt = update(AuthSession).where(
        AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
    )
    if only is not None:
        stmt = stmt.where(AuthSession.id == only)
    if keep is not None:
        stmt = stmt.where(AuthSession.id != keep)
    result = await db.execute(
        stmt.values(revoked_at=now, revoke_reason=reason).execution_options(
            synchronize_session=False
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def lock_refresh_token(
    db: AsyncSession, token_hash: str
) -> tuple[RefreshToken, AuthSession] | None:
    """Row-locks the token so two parallel refreshes with it cannot both succeed."""
    row = (
        await db.execute(
            select(RefreshToken, AuthSession)
            .join(AuthSession, AuthSession.id == RefreshToken.session_id)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update(of=RefreshToken)
        )
    ).first()
    return (row[0], row[1]) if row else None


# ---------------------------------------------------------------- addresses


async def list_addresses(db: AsyncSession, user_id: uuid.UUID) -> Sequence[Address]:
    return (
        await db.scalars(
            select(Address)
            .where(Address.user_id == user_id, Address.deleted_at.is_(None))
            .order_by(Address.is_default.desc(), Address.created_at.desc())
        )
    ).all()


async def count_addresses(db: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.count()).where(Address.user_id == user_id, Address.deleted_at.is_(None))
        )
        or 0
    )


async def get_address(
    db: AsyncSession, user_id: uuid.UUID, address_id: uuid.UUID
) -> Address | None:
    return await db.scalar(
        select(Address).where(
            Address.id == address_id, Address.user_id == user_id, Address.deleted_at.is_(None)
        )
    )


async def clear_default_address(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(Address)
        .where(Address.user_id == user_id, Address.is_default.is_(True))
        .values(is_default=False)
        .execution_options(synchronize_session="fetch")
    )


# ---------------------------------------------------------------- admin


async def search_users(
    db: AsyncSession, q: str | None, status: str | None, role: str | None, offset: int, limit: int
) -> Sequence[User]:
    stmt = select(User).where(User.deleted_at.is_(None))
    if q:
        pattern = f"%{q.replace('%', '').replace('_', '')}%"
        stmt = stmt.where(
            (User.email.ilike(pattern))
            | (User.phone.ilike(pattern))
            | (User.full_name.ilike(pattern))
        )
    if status:
        stmt = stmt.where(User.status == status)
    if role:
        stmt = stmt.where(
            User.id.in_(
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.code == role)
            )
        )
    return (
        await db.scalars(stmt.order_by(User.created_at.desc()).offset(offset).limit(limit))
    ).all()


async def remove_user_role(db: AsyncSession, user_id: uuid.UUID, role_id: uuid.UUID) -> int:
    result = await db.execute(
        delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


async def count_role_holders(db: AsyncSession, role_id: uuid.UUID) -> int:
    n = await db.scalar(select(func.count()).where(UserRole.role_id == role_id))
    return int(n or 0)


async def all_roles(db: AsyncSession) -> Sequence[Role]:
    return (await db.scalars(select(Role).order_by(Role.scope, Role.code))).all()
