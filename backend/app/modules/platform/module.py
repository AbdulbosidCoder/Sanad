"""Self-description of the `platform` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.platform.api import router

MODULE = ModuleInfo(
    name="platform",
    summary="Панель эксплуатации: фоновые очереди, их сбои и перезапуск; позже настройки.",
    router=router,
    depends_on=("i18n", "notifications", "audit"),
    emits=(),
    listens_to=(),
    tables=(),  # platform settings and feature flags come later
)
