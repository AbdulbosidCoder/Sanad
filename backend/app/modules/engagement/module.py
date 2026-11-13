"""Self-description of the `engagement` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.engagement.api import router

MODULE = ModuleInfo(
    name="engagement",
    summary="Избранное и просмотры товаров.",
    router=router,
    depends_on=("catalog",),
    emits=("ProductViewed",),
    listens_to=(),
    tables=("favorites", "product_views"),
)
