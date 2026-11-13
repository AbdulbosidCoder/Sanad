"""Self-description of the `support` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.support.api import router

MODULE = ModuleInfo(
    name="support",
    summary="Тикеты поддержки и переписка.",
    router=router,
    depends_on=("identity", "orders"),
    emits=("TicketCreated", "TicketReplied"),
    listens_to=(),
    tables=("support_tickets", "support_messages"),
)
