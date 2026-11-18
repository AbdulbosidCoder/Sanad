"""Self-description of the `recommendations` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.recommendations.api import router

MODULE = ModuleInfo(
    name="recommendations",
    summary="Главная страница и подборки: для вас, новинки, скидки, тренды, хиты, похожие.",
    router=router,
    depends_on=("engagement", "orders", "catalog"),
    emits=(),
    listens_to=(),
    tables=(),  # V1 computes on the fly; a cached table comes with the V2 model
)
