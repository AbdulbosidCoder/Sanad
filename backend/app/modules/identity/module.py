"""Self-description of the `identity` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.identity.api import router

MODULE = ModuleInfo(
    name="identity",
    summary="Регистрация, вход, токены и сессии, роли и права (RBAC).",
    router=router,
    depends_on=(),
    emits=("UserRegistered", "LoginSucceeded", "LoginFailed"),
    listens_to=(),
    tables=(
        "users",
        "roles",
        "permissions",
        "user_roles",
        "sessions",
        "refresh_tokens",
        "user_credentials",
        "addresses",
    ),
)
