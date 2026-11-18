"""Self-description of the `identity` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.identity import service
from app.modules.identity.api import router

MODULE = ModuleInfo(
    name="identity",
    summary="Регистрация, вход, токены и сессии, роли и права (RBAC).",
    router=router,
    depends_on=("audit",),
    emits=("UserRegistered", "LoginSucceeded", "LoginFailed"),
    listens_to=(),
    tables=(
        "users",
        "roles",
        "permissions",
        "role_permissions",
        "user_roles",
        "sessions",
        "refresh_tokens",
        "user_credentials",
        "addresses",
    ),
    setup=service.setup,  # installs the principal loader into core.auth
    on_startup=service.startup,  # writes the role/permission catalog (rbac.py)
)
