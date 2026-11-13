"""Self-description of the `i18n` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.i18n.api import router

MODULE = ModuleInfo(
    name="i18n",
    summary="Переводы контента (автоперевод описаний товаров на uz/ru/en, ручные правки).",
    router=router,
    depends_on=("catalog",),
    emits=("TranslationReady",),
    listens_to=("ProductCreated", "ProductUpdated"),
    tables=("product_translations", "category_translations", "translation_jobs"),
)
