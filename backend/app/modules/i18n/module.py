"""Self-description of the `i18n` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.i18n import service
from app.modules.i18n.api import router

MODULE = ModuleInfo(
    name="i18n",
    summary="Переводы товаров на uz/ru/en: автоперевод в фоне, ручные правки продавца.",
    router=router,
    depends_on=("catalog", "stores"),
    emits=("TranslationReady",),
    listens_to=("ProductCreated", "ProductUpdated"),
    tables=("product_translations", "translation_jobs"),
    setup=service.setup,  # queues jobs on product events, plugs translations into catalog
)
