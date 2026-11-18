"""Business logic of the `search` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

The index (``search_documents``) is rebuilt for a product whenever catalog or i18n
reports a change, in the same transaction. ``setup`` also plugs the matcher into the
catalog, so ``GET /products?q=`` uses full-text search with typo tolerance.
"""

import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.events import publish, subscribe
from app.core.pagination import Page
from app.modules.catalog import service as catalog
from app.modules.catalog.events import ProductArchived, ProductCreated, ProductUpdated
from app.modules.catalog.service import CategoryOut, ProductCard
from app.modules.i18n import service as i18n
from app.modules.i18n.events import TranslationReady
from app.modules.search import repository as repo
from app.modules.search.events import SearchPerformed
from app.modules.search.schemas import HistoryItem, PopularQuery, Suggestion, SuggestOut

MODULE = "search"
MAX_TOKENS = 8
_WORD = re.compile(r"\w+", re.UNICODE)


def normalize(query: str) -> str:
    """Lower-case words only: "Nike  Air-Max!" -> "nike air max"."""
    return " ".join(_WORD.findall(query.lower().replace("_", " ")))[:100]


def _tokens(norm: str) -> list[str]:
    return norm.split()[:MAX_TOKENS]


def matcher(query: str) -> Any:
    norm = normalize(query)
    return repo.match(_tokens(norm), norm)


def setup() -> None:
    for event in (ProductCreated, ProductUpdated, ProductArchived):
        subscribe(event, on_product_changed)
    subscribe(TranslationReady, on_product_changed)
    catalog.set_search_matcher(matcher)


# ---------------------------------------------------------------- index


async def reindex(db: AsyncSession, product_id: uuid.UUID) -> None:
    fields = await catalog.search_fields(db, product_id)
    if fields is None:
        await repo.delete_document(db, product_id)
        return
    parts = [fields.title, fields.brand or "", *fields.categories, fields.description]
    for _, title, description in await i18n.texts_of(db, product_id):
        parts += [title, description]
    document = " ".join(normalize(p) for p in parts if p)
    await repo.upsert_document(db, product_id, document)


async def on_product_changed(
    db: AsyncSession, event: ProductCreated | ProductUpdated | ProductArchived | TranslationReady
) -> None:
    await reindex(db, event.product_id)


async def is_empty(db: AsyncSession) -> bool:
    return await repo.document_count(db) == 0


async def reindex_all(db: AsyncSession) -> int:
    """Rebuilds the whole index (after renaming brands/categories, or for old databases)."""
    ids = await catalog.all_product_ids(db)
    for product_id in ids:
        await reindex(db, product_id)
    await db.commit()
    return len(ids)


# ---------------------------------------------------------------- buyer API


async def search(
    db: AsyncSession,
    principal: Principal | None,
    *,
    q: str,
    locale: str,
    category: str | None,
    brands: Sequence[str],
    sizes: Sequence[str],
    price_min: Decimal | None,
    price_max: Decimal | None,
    in_stock: bool | None,
    sort: Any,
    offset: int,
    limit: int,
) -> Page[ProductCard]:
    page = await catalog.list_products(
        db,
        locale=locale,
        category=category,
        brands=brands,
        store=None,
        q=q,
        price_min=price_min,
        price_max=price_max,
        in_stock=in_stock,
        rating_min=None,
        sizes=sizes,
        sort=sort,
        offset=offset,
        limit=limit,
    )
    norm = normalize(q)
    if offset == 0 and norm:  # count a search once, not for every next page
        if principal is not None:
            await repo.remember(db, principal.user_id, norm)
        await publish(
            db, SearchPerformed(norm, principal.user_id if principal else None, len(page.items))
        )
        await db.commit()
    return page


def _flatten(tree: list[CategoryOut]) -> list[CategoryOut]:
    out: list[CategoryOut] = []
    for c in tree:
        out.append(c)
        out.extend(_flatten(c.children))
    return out


async def suggest(
    db: AsyncSession, principal: Principal | None, q: str, locale: str, limit: int = 10
) -> SuggestOut:
    """As-you-type hints: own past queries, brands, categories, then products."""
    norm = normalize(q)
    if not norm:
        return SuggestOut(items=[])
    items: list[Suggestion] = []
    if principal is not None:
        items += [
            Suggestion(kind="history", text=h.query)
            for h in await repo.history(db, principal.user_id, norm, 3)
        ]
    items += [
        Suggestion(kind="brand", text=b.name, slug=b.slug)
        for b in await catalog.list_brands(db)
        if norm in normalize(b.name)
    ][:3]
    items += [
        Suggestion(kind="category", text=c.name, slug=c.slug)
        for c in _flatten(await catalog.list_categories(db, locale))
        if norm in normalize(c.name)
    ][:3]
    ids = await repo.matching_ids(db, _tokens(norm), norm, limit)
    items += [
        Suggestion(kind="product", text=card.title, slug=card.slug)
        for card in await catalog.product_cards(db, ids, locale)
    ]
    return SuggestOut(items=items[:limit])


async def my_history(db: AsyncSession, principal: Principal, limit: int = 20) -> list[HistoryItem]:
    return [
        HistoryItem(query=h.query) for h in await repo.history(db, principal.user_id, "", limit)
    ]


async def clear_history(db: AsyncSession, principal: Principal, query: str | None) -> None:
    await repo.forget(db, principal.user_id, normalize(query) if query is not None else None)
    await db.commit()


async def popular_queries(db: AsyncSession, days: int = 7, limit: int = 10) -> list[PopularQuery]:
    since = datetime.now(UTC) - timedelta(days=days)
    return [PopularQuery(query=q, count=n) for q, n in await repo.popular(db, since, limit)]
