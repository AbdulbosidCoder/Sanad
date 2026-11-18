"""HTTP endpoints of the `identity` module. Business logic lives in service.py.

Token transport (docs/architecture/05-api-architecture.md, 5.2):
- the access token is returned in the body; the client keeps it in memory and sends
  ``Authorization: Bearer``;
- the refresh token is only in an HttpOnly cookie scoped to ``/api/v1/auth``;
- ``/auth/refresh`` and ``/auth/logout`` need ``X-CSRF-Token`` equal to the readable
  ``sanad_csrf`` cookie (double submit), because they are authenticated by cookie.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    Principal,
    get_principal,
    require_permission,
    require_sensitive_action,
)
from app.core.config import get_settings
from app.core.db import get_session
from app.core.errors import AppError
from app.core.modules import module_router
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, decode_cursor
from app.core.security import tokens_equal
from app.modules.identity import service
from app.modules.identity.schemas import (
    AddressIn,
    AddressOut,
    AddressUpdate,
    AdminUserOut,
    BlockIn,
    LoginIn,
    MeOut,
    MeUpdate,
    PasswordChangeIn,
    RegisterIn,
    RoleOut,
    SessionOut,
    TokenOut,
)

router = module_router("identity")

REFRESH_COOKIE = "sanad_refresh"
CSRF_COOKIE = "sanad_csrf"
CSRF_HEADER = "X-CSRF-Token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _client(request: Request) -> service.ClientInfo:
    return service.ClientInfo(
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", ""),
    )


def _set_auth_cookies(response: Response, tokens: service.IssuedTokens) -> None:
    secure = get_settings().auth_cookie_secure
    max_age = max(0, int((tokens.session_expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.set_cookie(
        CSRF_COOKIE,
        tokens.csrf_token,
        max_age=max_age,
        path="/",
        httponly=False,  # the frontend reads it and echoes it in X-CSRF-Token
        secure=secure,
        samesite="lax",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE, path="/")


def _check_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get(CSRF_HEADER, "")
    if not cookie or not header or not tokens_equal(cookie, header):
        raise AppError("identity", "CSRF_FAILED", f"Missing or wrong {CSRF_HEADER}", status=403)


def _token_out(response: Response, tokens: service.IssuedTokens) -> TokenOut:
    _set_auth_cookies(response, tokens)
    return TokenOut(
        access_token=tokens.access_token, expires_in=tokens.expires_in, csrf_token=tokens.csrf_token
    )


# ---------------------------------------------------------------- auth


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterIn, request: Request, response: Response, db: AsyncSession = Depends(get_session)
) -> TokenOut:
    """Creates a customer account and signs it in."""
    return _token_out(response, await service.register(db, data, _client(request)))


@router.post("/auth/login")
async def login(
    data: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_session)
) -> TokenOut:
    """``login`` is an email or a phone in international format."""
    return _token_out(response, await service.login(db, data, _client(request)))


@router.post("/auth/refresh")
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_session)
) -> TokenOut:
    """New access token + rotated refresh cookie. Call it once at a time per browser:
    replaying an old refresh token ends the session."""
    _check_csrf(request)
    tokens = await service.refresh(db, request.cookies.get(REFRESH_COOKIE), _client(request))
    return _token_out(response, tokens)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(request: Request, db: AsyncSession = Depends(get_session)) -> Response:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    if refresh_token:
        _check_csrf(request)
        await service.logout(db, refresh_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(response)
    return response


# ---------------------------------------------------------------- profile


@router.get("/me")
async def get_me(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> MeOut:
    return await service.get_me(db, principal)


@router.patch("/me")
async def update_me(
    data: MeUpdate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> MeOut:
    return await service.update_me(db, principal, data)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def change_password(
    data: PasswordChangeIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> None:
    """Changes the password and signs out all other devices."""
    await service.change_password(db, principal, data)


@router.get("/me/sessions")
async def list_sessions(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> list[SessionOut]:
    return await service.list_sessions(db, principal)


@router.delete(
    "/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def revoke_session(
    session_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> None:
    await service.revoke_session(db, principal, session_id)


# ---------------------------------------------------------------- addresses


@router.get("/me/addresses")
async def list_addresses(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> list[AddressOut]:
    return await service.list_addresses(db, principal)


@router.post("/me/addresses", status_code=status.HTTP_201_CREATED)
async def create_address(
    data: AddressIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> AddressOut:
    return await service.create_address(db, principal, data)


@router.patch("/me/addresses/{address_id}")
async def update_address(
    address_id: uuid.UUID,
    data: AddressUpdate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> AddressOut:
    return await service.update_address(db, principal, address_id, data)


@router.delete(
    "/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_address(
    address_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_address(db, principal, address_id)


# ---------------------------------------------------------------- admin


@router.get("/admin/users")
async def admin_users(
    q: str | None = Query(None, max_length=100, description="email, phone or name"),
    status_: Literal["active", "blocked", "pending"] | None = Query(None, alias="status"),
    role: str | None = Query(None, max_length=64),
    cursor: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    _: Principal = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> list[AdminUserOut]:
    return await service.admin_users(db, q, status_, role, decode_cursor(cursor, "identity"), limit)


@router.get("/admin/users/{user_id}")
async def admin_user(
    user_id: uuid.UUID,
    _: Principal = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> AdminUserOut:
    return await service.admin_user(db, user_id)


@router.post("/admin/users/{user_id}/block")
async def block(
    user_id: uuid.UUID,
    data: BlockIn,
    actor: Principal = Depends(require_sensitive_action("users.block")),
    db: AsyncSession = Depends(get_session),
) -> AdminUserOut:
    """Blocks the account and signs it out everywhere (audited)."""
    return await service.block_user(db, actor, user_id, data)


@router.post("/admin/users/{user_id}/unblock")
async def unblock(
    user_id: uuid.UUID,
    actor: Principal = Depends(require_sensitive_action("users.block")),
    db: AsyncSession = Depends(get_session),
) -> AdminUserOut:
    return await service.unblock_user(db, actor, user_id)


@router.get("/admin/roles")
async def roles(
    _: Principal = Depends(require_permission("users.read")),
    db: AsyncSession = Depends(get_session),
) -> list[RoleOut]:
    return await service.list_roles(db)


@router.put("/admin/users/{user_id}/roles/{role_code}")
async def grant(
    user_id: uuid.UUID,
    role_code: str,
    actor: Principal = Depends(require_sensitive_action("rbac.manage")),
    db: AsyncSession = Depends(get_session),
) -> AdminUserOut:
    return await service.admin_grant_role(db, actor, user_id, role_code)


@router.delete("/admin/users/{user_id}/roles/{role_code}")
async def revoke(
    user_id: uuid.UUID,
    role_code: str,
    actor: Principal = Depends(require_sensitive_action("rbac.manage")),
    db: AsyncSession = Depends(get_session),
) -> AdminUserOut:
    return await service.admin_revoke_role(db, actor, user_id, role_code)
