"""Self-description of the `reviews` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.reviews.api import router

MODULE = ModuleInfo(
    name="reviews",
    summary="Отзывы и рейтинги: только после доставки, ответ магазина, модерация.",
    router=router,
    depends_on=("orders", "catalog", "identity", "stores"),
    emits=("ReviewPublished",),
    listens_to=(),
    tables=("reviews",),
)
