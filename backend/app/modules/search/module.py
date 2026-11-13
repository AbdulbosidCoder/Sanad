"""Self-description of the `search` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.search.api import router

MODULE = ModuleInfo(
    name="search",
    summary="Поиск, фильтры, сортировки, автодополнение, история поиска.",
    router=router,
    depends_on=("catalog", "i18n"),
    emits=("SearchPerformed",),
    listens_to=("ProductCreated", "ProductUpdated", "ProductArchived", "TranslationReady"),
    tables=("search_history",),
)
