"""Self-description of the `recommendations` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.recommendations.api import router

MODULE = ModuleInfo(
    name="recommendations",
    summary="Персональные подборки, тренды, хиты недели.",
    router=router,
    depends_on=("engagement", "orders", "catalog"),
    emits=(),
    listens_to=("ProductViewed", "OrderPlaced"),
    tables=("recommendations",),
)
