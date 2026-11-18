"""Self-description of the `search` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.search import service
from app.modules.search.api import router

MODULE = ModuleInfo(
    name="search",
    summary="Полнотекстовый поиск на всех языках с опечатками, подсказки, история поиска.",
    router=router,
    depends_on=("catalog", "i18n"),
    emits=("SearchPerformed",),
    listens_to=("ProductCreated", "ProductUpdated", "ProductArchived", "TranslationReady"),
    tables=("search_documents", "search_history"),
    setup=service.setup,  # reindexes on product events, plugs the matcher into catalog
)
