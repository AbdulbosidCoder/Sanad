"""Self-description of the `analytics` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.analytics.api import router

MODULE = ModuleInfo(
    name="analytics",
    summary="Аналитика продавца: продажи, выручка, просмотры, конверсия, бестселлеры.",
    router=router,
    depends_on=("orders", "engagement", "search"),
    emits=(),
    listens_to=("OrderPlaced", "ProductViewed", "SearchPerformed"),
    tables=("seller_daily_stats", "product_daily_stats"),
)
