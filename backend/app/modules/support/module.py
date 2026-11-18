"""Self-description of the `support` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.support.api import router

MODULE = ModuleInfo(
    name="support",
    summary="Тикеты поддержки: переписка, внутренние заметки, очередь, назначение.",
    router=router,
    depends_on=("identity", "orders", "audit"),
    emits=("TicketCreated", "TicketReplied"),
    listens_to=(),
    tables=("support_tickets", "support_messages"),
)
