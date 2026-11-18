"""Business logic of the `identity` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, set_principal_loader
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import AppError
from app.core.models import uuid7
from app.core.security import (
    AccessClaims,
    create_access_token,
    hash_password,
    hash_token,
    new_token,
    password_needs_rehash,
    verify_password,
)
from app.modules.identity import repository as repo
from app.modules.identity.models import Address, AuthSession, RefreshToken, User, UserCredential
from app.modules.identity.rbac import CUSTOMER, PERMISSIONS, ROLES, ROLES_BY_CODE
from app.modules.identity.schemas import (
    AddressIn,
    AddressOut,
    AddressUpdate,
    LoginIn,
    MeOut,
    MeUpdate,
    PasswordChangeIn,
    RegisterIn,
    SessionOut,
)
from app.modules.identity.schemas import normalize_phone as normalize_phone  # public helper

MODULE = "identity"
MAX_ADDRESSES = 20

logger = logging.getLogger("app.modules.identity")


def _error(code: str, detail: str, status: int) -> AppError:
    return AppError(MODULE, code, detail, status=status)


def _now() -> datetime:
    return datetime.now(UTC)


def _log(msg: str, **fields: object) -> None:
    logger.info(msg, extra={"extra_fields": {k: str(v) for k, v in fields.items()}})


@dataclass(frozen=True)
class ClientInfo:
    ip: str | None
    user_agent: str


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    csrf_token: str
    session_expires_at: datetime


# ---------------------------------------------------------------- module wiring


async def load_principal(db: AsyncSession, claims: AccessClaims) -> Principal | None:
    """Installed into core.auth: turns a valid JWT into the caller's current rights."""
    session = await repo.get_live_session(db, claims.session_id, claims.user_id, _now())
    if session is None:
        return None
    roles, permissions = await repo.platform_roles_and_permissions(db, claims.user_id)
    return Principal(claims.user_id, claims.session_id, roles, permissions)


def setup() -> None:
    set_principal_loader(load_principal)


async def startup() -> None:
    async with get_sessionmaker()() as db:
        await sync_rbac(db)
        await db.commit()


async def sync_rbac(db: AsyncSession) -> None:
    """Writes the role/permission catalog from rbac.py. Safe to run any number of times."""
    permission_ids = await repo.upsert_permissions(db, PERMISSIONS)
    for role in ROLES:
        role_id = await repo.upsert_role(db, role.code, role.scope, role.description)
        await repo.set_role_permissions(db, role_id, [permission_ids[p] for p in role.permissions])


async def grant_role(
    db: AsyncSession, user_id: uuid.UUID, role_code: str, granted_by: uuid.UUID | None = None
) -> None:
    definition = ROLES_BY_CODE.get(role_code)
    if definition is not None and definition.scope != "platform":
        raise _error("STORE_ROLE", "Store roles are granted through store membership", 400)
    role = await repo.get_role_by_code(db, role_code)
    if role is None or role.scope != "platform":
        raise _error("ROLE_NOT_FOUND", f"Unknown platform role: {role_code}", 404)
    await repo.add_user_role(db, user_id, role.id, granted_by)
    await db.commit()
    _log("role granted", user_id=user_id, role=role_code, granted_by=granted_by)


async def find_user_id(db: AsyncSession, login: str) -> uuid.UUID | None:
    user = await _find_by_login(db, login)
    return user.id if user else None


# ---------------------------------------------------------------- tokens


def _issue(db: AsyncSession, session: AuthSession) -> tuple[IssuedTokens, uuid.UUID]:
    refresh_token = new_token()
    token_id = uuid7()
    db.add(RefreshToken(id=token_id, session_id=session.id, token_hash=hash_token(refresh_token)))
    access_token, ttl = create_access_token(session.user_id, session.id)
    tokens = IssuedTokens(access_token, ttl, refresh_token, new_token(), session.expires_at)
    return tokens, token_id


def _open_session(db: AsyncSession, user: User, client: ClientInfo) -> IssuedTokens:
    now = _now()
    session = AuthSession(
        id=uuid7(),
        user_id=user.id,
        device_info=client.user_agent[:255],
        ip=client.ip,
        expires_at=now + timedelta(days=get_settings().session_ttl_days),
        last_seen_at=now,
    )
    db.add(session)
    tokens, _ = _issue(db, session)
    return tokens


# ---------------------------------------------------------------- auth flows


async def _create_user(db: AsyncSession, data: RegisterIn) -> User:
    """Inserts a customer with a password (flushed, not committed)."""
    if data.email and await repo.email_exists(db, data.email):
        raise _error("EMAIL_TAKEN", "This email is already registered", 409)
    if data.phone and await repo.phone_exists(db, data.phone):
        raise _error("PHONE_TAKEN", "This phone is already registered", 409)
    role = await repo.get_role_by_code(db, CUSTOMER)
    if role is None:
        raise RuntimeError("RBAC catalog is not in the database: restart the API or run sync-rbac")

    password_hash = await asyncio.to_thread(hash_password, data.password)
    user = User(
        id=uuid7(),
        email=data.email,
        phone=data.phone,
        full_name=data.full_name,
        locale=data.locale,
    )
    db.add(user)
    db.add(UserCredential(user_id=user.id, type="password", secret=password_hash))
    try:
        await db.flush()
    except IntegrityError as exc:  # a parallel registration won the race
        await db.rollback()
        raise _error("ACCOUNT_EXISTS", "This email or phone is already registered", 409) from exc
    await repo.add_user_role(db, user.id, role.id)
    return user


async def register(db: AsyncSession, data: RegisterIn, client: ClientInfo) -> IssuedTokens:
    user = await _create_user(db, data)
    user.last_login_at = _now()
    tokens = _open_session(db, user, client)
    await db.commit()
    _log("user registered", user_id=user.id)
    return tokens


async def create_user(db: AsyncSession, data: RegisterIn) -> uuid.UUID:
    """Creates a customer account without signing it in (demo data, admin tools).
    The caller commits."""
    user = await _create_user(db, data)
    _log("user created", user_id=user.id)
    return user.id


def store_role_permissions(role_code: str) -> frozenset[str]:
    """Permissions of a store-scope role (``seller_owner`` ...). Unknown role -> none."""
    role = ROLES_BY_CODE.get(role_code)
    if role is None or role.scope != "store":
        return frozenset()
    return role.permissions


STORE_ROLES: tuple[str, ...] = tuple(r.code for r in ROLES if r.scope == "store")


async def user_brief(db: AsyncSession, user_id: uuid.UUID) -> tuple[str | None, str] | None:
    """(email, full_name) of a user, for staff lists. None if the user does not exist."""
    user = await repo.get_user(db, user_id)
    return (user.email, user.full_name) if user else None


async def _find_by_login(db: AsyncSession, login: str) -> User | None:
    if "@" in login:
        return await repo.find_user_by_email(db, login)
    try:
        return await repo.find_user_by_phone(db, normalize_phone(login))
    except ValueError:
        return None


async def login(db: AsyncSession, data: LoginIn, client: ClientInfo) -> IssuedTokens:
    settings = get_settings()
    now = _now()
    user = await _find_by_login(db, data.login)
    if user is not None and user.locked_until is not None and user.locked_until > now:
        raise _error("TOO_MANY_ATTEMPTS", "Too many failed attempts, try again later", 429)

    credential = await repo.get_password_credential(db, user.id) if user else None
    secret = credential.secret if credential else None
    if not await asyncio.to_thread(verify_password, secret, data.password):
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.login_max_failures:
                user.failed_login_count = 0
                user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            await db.commit()
        _log("login failed", user_id=user.id if user else "-", ip=client.ip)
        raise _error("INVALID_CREDENTIALS", "Wrong login or password", 401)

    if user is None or credential is None:  # unreachable: verify fails without a credential
        raise _error("INVALID_CREDENTIALS", "Wrong login or password", 401)
    if user.status == "blocked":
        raise _error("ACCOUNT_BLOCKED", "This account is blocked", 403)
    if user.status != "active":
        raise _error("ACCOUNT_INACTIVE", "This account is not active", 403)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    credential.last_used_at = now
    if password_needs_rehash(credential.secret):
        credential.secret = await asyncio.to_thread(hash_password, data.password)
    tokens = _open_session(db, user, client)
    await db.commit()
    _log("login succeeded", user_id=user.id, ip=client.ip)
    return tokens


_SESSION_ENDED = "Session ended, sign in again"


async def refresh(db: AsyncSession, refresh_token: str | None, client: ClientInfo) -> IssuedTokens:
    """Rotates the refresh token. Presenting an already used token means it was copied:
    the whole session is revoked (ADR 0005)."""
    if not refresh_token:
        raise _error("INVALID_REFRESH_TOKEN", _SESSION_ENDED, 401)
    found = await repo.lock_refresh_token(db, hash_token(refresh_token))
    if found is None:
        raise _error("INVALID_REFRESH_TOKEN", _SESSION_ENDED, 401)
    token, session = found
    now = _now()

    if token.used_at is not None:
        if session.revoked_at is None:
            session.revoked_at = now
            session.revoke_reason = "refresh_reuse"
            await db.commit()
            logger.warning(
                "refresh token reuse: session revoked",
                extra={"extra_fields": {"session_id": str(session.id), "ip": str(client.ip)}},
            )
        raise _error("REFRESH_TOKEN_REUSED", _SESSION_ENDED, 401)

    if session.revoked_at is not None or session.expires_at <= now:
        raise _error("SESSION_EXPIRED", _SESSION_ENDED, 401)
    user = await repo.get_user(db, session.user_id)
    if user is None or user.status != "active":
        raise _error("SESSION_EXPIRED", _SESSION_ENDED, 401)

    tokens, new_id = _issue(db, session)
    token.used_at = now
    token.replaced_by = new_id
    session.last_seen_at = now
    session.ip = client.ip
    await db.commit()
    return tokens


async def logout(db: AsyncSession, refresh_token: str | None) -> None:
    """Idempotent: an unknown or missing token is not an error."""
    if not refresh_token:
        return
    found = await repo.lock_refresh_token(db, hash_token(refresh_token))
    if found is None:
        return
    _, session = found
    if session.revoked_at is None:
        session.revoked_at = _now()
        session.revoke_reason = "logout"
        await db.commit()


# ---------------------------------------------------------------- profile


async def _current_user(db: AsyncSession, principal: Principal) -> User:
    user = await repo.get_user(db, principal.user_id)
    if user is None:  # deleted between the auth check and now
        raise _error("UNAUTHENTICATED", _SESSION_ENDED, 401)
    return user


def _me(user: User, principal: Principal) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        phone=user.phone,
        full_name=user.full_name,
        locale=user.locale,  # guarded by a CHECK constraint
        status=user.status,
        email_verified=user.email_verified,
        phone_verified=user.phone_verified,
        created_at=user.created_at,
        roles=sorted(principal.roles),
        permissions=sorted(principal.permissions),
    )


async def get_me(db: AsyncSession, principal: Principal) -> MeOut:
    return _me(await _current_user(db, principal), principal)


async def update_me(db: AsyncSession, principal: Principal, data: MeUpdate) -> MeOut:
    user = await _current_user(db, principal)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, field, value)
    await db.commit()
    return _me(user, principal)


async def change_password(db: AsyncSession, principal: Principal, data: PasswordChangeIn) -> None:
    """Also signs out every other device."""
    credential = await repo.get_password_credential(db, principal.user_id)
    secret = credential.secret if credential else None
    if credential is None or not await asyncio.to_thread(
        verify_password, secret, data.current_password
    ):
        # 400, not 401: a 401 would make the client think its access token expired.
        raise _error("WRONG_PASSWORD", "Current password is wrong", 400)
    credential.secret = await asyncio.to_thread(hash_password, data.new_password)
    await repo.revoke_sessions(
        db, principal.user_id, _now(), "password_changed", keep=principal.session_id
    )
    await db.commit()
    _log("password changed", user_id=principal.user_id)


async def list_sessions(db: AsyncSession, principal: Principal) -> list[SessionOut]:
    sessions = await repo.list_live_sessions(db, principal.user_id, _now())
    return [
        SessionOut(
            id=s.id,
            device_info=s.device_info,
            ip=str(s.ip) if s.ip is not None else None,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            expires_at=s.expires_at,
            current=s.id == principal.session_id,
        )
        for s in sessions
    ]


async def revoke_session(db: AsyncSession, principal: Principal, session_id: uuid.UUID) -> None:
    revoked = await repo.revoke_sessions(
        db, principal.user_id, _now(), "user_revoked", only=session_id
    )
    if not revoked:
        raise _error("SESSION_NOT_FOUND", "Session not found", 404)
    await db.commit()


# ---------------------------------------------------------------- addresses


async def list_addresses(db: AsyncSession, principal: Principal) -> list[AddressOut]:
    return [AddressOut.model_validate(a) for a in await repo.list_addresses(db, principal.user_id)]


async def _own_address(db: AsyncSession, principal: Principal, address_id: uuid.UUID) -> Address:
    address = await repo.get_address(db, principal.user_id, address_id)
    if address is None:  # someone else's address looks exactly like a missing one
        raise _error("ADDRESS_NOT_FOUND", "Address not found", 404)
    return address


async def create_address(db: AsyncSession, principal: Principal, data: AddressIn) -> AddressOut:
    count = await repo.count_addresses(db, principal.user_id)
    if count >= MAX_ADDRESSES:
        raise _error("ADDRESS_LIMIT", f"At most {MAX_ADDRESSES} addresses", 409)
    make_default = data.is_default or count == 0
    if make_default:
        await repo.clear_default_address(db, principal.user_id)
    address = Address(
        id=uuid7(),
        user_id=principal.user_id,
        **data.model_dump(exclude={"is_default"}),
        is_default=make_default,
    )
    db.add(address)
    await db.commit()
    return AddressOut.model_validate(address)


async def update_address(
    db: AsyncSession, principal: Principal, address_id: uuid.UUID, data: AddressUpdate
) -> AddressOut:
    address = await _own_address(db, principal, address_id)
    for field, value in data.model_dump(exclude_unset=True, exclude={"is_default"}).items():
        if value is not None or field == "line2":  # line2 is optional: null clears it
            setattr(address, field, value)
    if data.is_default and not address.is_default:
        await repo.clear_default_address(db, principal.user_id)
        address.is_default = True
    await db.commit()
    return AddressOut.model_validate(address)


async def delete_address(db: AsyncSession, principal: Principal, address_id: uuid.UUID) -> None:
    address = await _own_address(db, principal, address_id)
    was_default = address.is_default
    address.deleted_at = _now()
    address.is_default = False
    await db.flush()
    if was_default:
        remaining = await repo.list_addresses(db, principal.user_id)
        if remaining:
            remaining[0].is_default = True
    await db.commit()
