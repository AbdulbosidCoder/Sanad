"""Self-description of the `platform` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.platform.api import router

MODULE = ModuleInfo(
    name="platform",
    summary="Настройки платформы и feature flags.",
    router=router,
    depends_on=(),
    emits=(),
    listens_to=(),
    tables=("platform_settings",),
)
