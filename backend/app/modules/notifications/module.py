"""Self-description of the `notifications` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.notifications.api import router

MODULE = ModuleInfo(
    name="notifications",
    summary="Уведомления: in-app, email, позже SMS и push.",
    router=router,
    depends_on=("identity",),
    emits=(),
    listens_to=(
        "OrderPlaced",
        "PaymentSucceeded",
        "SellerOrderStatusChanged",
        "StockLow",
        "TicketReplied",
        "StoreApproved",
    ),
    tables=("notifications", "notification_preferences"),
)
