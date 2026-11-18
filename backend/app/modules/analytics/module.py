"""Self-description of the `analytics` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.analytics.api import router

MODULE = ModuleInfo(
    name="analytics",
    summary="Аналитика продавца: выручка, заказы, просмотры, конверсия, товары, рейтинг.",
    router=router,
    depends_on=("orders", "engagement", "catalog", "inventory", "reviews", "stores"),
    emits=(),
    listens_to=(),
    tables=(),  # V1 reads source tables; daily aggregates come in V2
)
