"""Self-description of the `reviews` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.reviews.api import router

MODULE = ModuleInfo(
    name="reviews",
    summary="Отзывы и рейтинги (только по купленным товарам).",
    router=router,
    depends_on=("orders", "catalog"),
    emits=("ReviewPublished",),
    listens_to=(),
    tables=("reviews",),
)
