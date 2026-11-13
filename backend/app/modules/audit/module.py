"""Self-description of the `audit` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.audit.api import router

MODULE = ModuleInfo(
    name="audit",
    summary="Неизменяемый журнал чувствительных действий.",
    router=router,
    depends_on=(),
    emits=(),
    listens_to=(),
    tables=("audit_logs",),
)
