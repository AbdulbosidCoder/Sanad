"""Self-description of the `orders` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.orders.api import router

MODULE = ModuleInfo(
    name="orders",
    summary="Checkout, родительский заказ и заказы продавцов, статусы, возвраты товара.",
    router=router,
    depends_on=("cart", "inventory", "payments", "stores", "audit"),
    emits=("OrderPlaced", "OrderCancelled", "SellerOrderStatusChanged"),
    listens_to=("PaymentSucceeded", "PaymentFailed", "RefundCompleted"),
    tables=("orders", "seller_orders", "order_items", "order_status_history", "return_requests"),
)
