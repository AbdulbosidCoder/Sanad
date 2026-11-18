"""Self-description of the `notifications` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.notifications import service
from app.modules.notifications.api import router

MODULE = ModuleInfo(
    name="notifications",
    summary="Уведомления: в приложении (колокольчик) и email; позже SMS и push.",
    router=router,
    depends_on=("identity", "stores"),
    emits=(),
    listens_to=(
        "OrderPlaced",
        "OrderPaid",
        "OrderCancelled",
        "SellerOrderStatusChanged",
        "RefundCompleted",
        "StockLow",
        "StoreApproved",
        "SellerApplicationRejected",
        "StoreSuspended",
        "TicketReplied",
    ),
    tables=("notifications", "notification_preferences", "email_outbox"),
    setup=service.setup,
)
