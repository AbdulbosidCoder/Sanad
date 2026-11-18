"""Self-description of the `catalog` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.catalog.api import router

MODULE = ModuleInfo(
    name="catalog",
    summary="Товары, варианты, категории, бренды, фото товара по ракурсам, модерация.",
    router=router,
    depends_on=("stores", "media", "audit"),
    emits=("ProductCreated", "ProductUpdated", "ProductArchived"),
    listens_to=(),
    tables=("products", "product_variants", "categories", "brands", "product_images"),
)
