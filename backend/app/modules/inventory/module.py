"""Self-description of the `inventory` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.inventory.api import router

MODULE = ModuleInfo(
    name="inventory",
    summary="Остатки, резервы под заказы, движение склада, low-stock.",
    router=router,
    depends_on=("catalog",),
    emits=("StockLow", "StockReserved"),
    listens_to=("OrderPlaced", "PaymentSucceeded", "OrderCancelled", "RefundCompleted"),
    tables=("inventory", "stock_reservations", "stock_movements"),
)
