"""Authentication and authorization dependencies shared by every module.

Flow on each request (docs/architecture/04-rbac-matrix.md, 4.1):
1. ``get_principal`` checks the access JWT, then asks the *principal loader* whether the
   session is still alive and which permissions the user has right now. A revoked session
   or a blocked user is rejected immediately, not when the 15-minute token expires.
2. ``require_permission("products.write")`` checks the permission.
3. Object-level checks (is this *your* order / store?) stay in each module's service and
   answer 404, not 403, so other people's objects are not revealed.

Core must not import business modules, so the loader is plugged in by the ``identity``
module at startup (``set_principal_loader``).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import AppError
from app.core.security import AccessClaims, InvalidAccessToken, decode_access_token

AUTH_MODULE = "identity"


@dataclass(frozen=True)
class Principal:
    """Who is calling. Built fresh from the database on every authenticated request."""

    user_id: uuid.UUID
    session_id: uuid.UUID
    roles: frozenset[str] = field(default_factory=frozenset)
    permissions: frozenset[str] = field(default_factory=frozenset)

    def has(self, permission: str) -> bool:
        return permission in self.permissions


PrincipalLoader = Callable[[AsyncSession, AccessClaims], Awaitable[Principal | None]]

_loader: PrincipalLoader | None = None


def set_principal_loader(loader: PrincipalLoader) -> None:
    global _loader
    _loader = loader


def _unauthenticated(detail: str = "Authentication required") -> AppError:
    return AppError(AUTH_MODULE, "UNAUTHENTICATED", detail, status=401)


_bearer = HTTPBearer(auto_error=False, description="Access token from POST /auth/login")


async def get_optional_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_session),
) -> Principal | None:
    """For endpoints that work for guests too. A *bad* token is still an error:
    the client must refresh it rather than silently become a guest."""
    if credentials is None:
        return None
    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidAccessToken as exc:
        raise _unauthenticated("Access token is invalid or expired") from exc
    if _loader is None:
        raise RuntimeError("principal loader is not installed (identity module not set up)")
    principal = await _loader(db, claims)
    if principal is None:
        raise _unauthenticated("Session is no longer active")
    return principal


async def get_principal(
    principal: Principal | None = Depends(get_optional_principal),
) -> Principal:
    if principal is None:
        raise _unauthenticated()
    return principal


def require_permission(*permissions: str) -> Callable[..., Awaitable[Principal]]:
    """Dependency: the caller must hold *all* listed permissions."""

    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        missing = [p for p in permissions if not principal.has(p)]
        if missing:
            raise AppError(AUTH_MODULE, "FORBIDDEN", "Not enough permissions", status=403)
        return principal

    return dependency


def require_sensitive_action(permission: str) -> Callable[..., Awaitable[Principal]]:
    """Dependency for actions marked 🔒 in the RBAC matrix.

    Today it equals ``require_permission``; it is the single place where V3 adds
    step-up confirmation (2FA), so endpoints must use it for 🔒 actions from day one.
    """
    return require_permission(permission)
