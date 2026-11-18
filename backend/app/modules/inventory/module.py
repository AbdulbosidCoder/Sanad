"""Self-description of the `inventory` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.inventory.api import router

MODULE = ModuleInfo(
    name="inventory",
    summary="Остатки, движение склада, low-stock (резервы под заказы — этап 5).",
    router=router,
    depends_on=("catalog", "stores"),
    emits=("StockLow", "StockReserved"),
    listens_to=("OrderPlaced", "PaymentSucceeded", "OrderCancelled", "RefundCompleted"),
    tables=("inventory", "stock_movements"),
)
