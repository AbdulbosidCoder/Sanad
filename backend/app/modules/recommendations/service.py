"""Business logic of the `recommendations` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

V1 computes blocks on the fly from views, favourites and sales (enough for a small
catalog). A cached ``recommendations`` table and a trained model are V2.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import AppError
from app.modules.catalog import service as catalog
from app.modules.catalog.service import ProductCard
from app.modules.engagement import service as engagement
from app.modules.orders import service as orders
from app.modules.recommendations.schemas import Block, HomeOut

MODULE = "recommendations"
BLOCK_SIZE = 12

TITLES: dict[str, dict[str, str]] = {
    "for_you": {"uz": "Siz uchun", "ru": "Для вас", "en": "For you"},
    "new": {"uz": "Yangi kelganlar", "ru": "Новинки", "en": "New arrivals"},
    "sale": {"uz": "Chegirmalar", "ru": "Скидки", "en": "On sale"},
    "trending": {"uz": "Ommabop", "ru": "Сейчас смотрят", "en": "Trending"},
    "bestsellers": {"uz": "Xitlar", "ru": "Хиты недели", "en": "Best sellers"},
    "similar": {"uz": "O'xshash", "ru": "Похожие товары", "en": "Similar"},
    "also_viewed": {
        "uz": "Buni ko'rganlar yana ko'rdi",
        "ru": "С этим товаром смотрят",
        "en": "People also viewed",
    },
}


def _block(key: str, locale: str, items: list[ProductCard]) -> Block:
    return Block(key=key, title=TITLES[key].get(locale, TITLES[key]["ru"]), items=items)


async def _newest(
    db: AsyncSession,
    locale: str,
    limit: int,
    category: str | None = None,
    brands: Sequence[str] = (),
) -> list[ProductCard]:
    page = await catalog.list_products(
        db,
        locale=locale,
        category=category,
        brands=brands,
        store=None,
        q=None,
        price_min=None,
        price_max=None,
        in_stock=True,
        rating_min=None,
        sizes=[],
        sort="newest",
        offset=0,
        limit=limit,
    )
    return page.items


def _unique(ids: list[uuid.UUID], exclude: set[uuid.UUID], limit: int) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for i in ids:
        if i not in exclude and i not in out:
            out.append(i)
    return out[:limit]


async def for_user(db: AsyncSession, user_id: uuid.UUID, locale: str) -> list[ProductCard]:
    """Things like what the buyer viewed, liked or bought — but not those very products."""
    seen = await engagement.recently_viewed_ids(db, user_id, 5)
    liked = await engagement.favorite_product_ids(db, user_id, 5)
    bought = await orders.bought_by_user(db, user_id, 5)
    seeds = _unique(seen + liked + bought, set(), 8)
    candidates: list[uuid.UUID] = []
    for seed in seeds:
        candidates += await engagement.also_viewed(db, seed, 6)
    exclude = set(seen) | set(bought)
    cards = await catalog.product_cards(db, _unique(candidates, exclude, BLOCK_SIZE), locale)
    if len(cards) < BLOCK_SIZE:  # fill with the same categories
        for card in await catalog.product_cards(db, seeds[:3], locale):
            more = await _newest(db, locale, BLOCK_SIZE, category=card.category.slug)
            known = exclude | {c.id for c in cards}
            cards += [c for c in more if c.id not in known]
    return cards[:BLOCK_SIZE]


async def home(db: AsyncSession, principal: Principal | None, locale: str) -> HomeOut:
    blocks: list[Block] = []
    if principal is not None:
        mine = await for_user(db, principal.user_id, locale)
        if mine:
            blocks.append(_block("for_you", locale, mine))
    newest = await _newest(db, locale, 48)
    blocks.append(_block("new", locale, newest[:BLOCK_SIZE]))
    sale = [
        c for c in newest if c.compare_at_price and c.min_price and c.compare_at_price > c.min_price
    ]
    if sale:
        blocks.append(_block("sale", locale, sale[:BLOCK_SIZE]))
    trending = [p for p, _ in await engagement.most_viewed(db, 7, BLOCK_SIZE)]
    if trending:
        blocks.append(_block("trending", locale, await catalog.product_cards(db, trending, locale)))
    best = [p for p, _ in await orders.best_sellers(db, 7, BLOCK_SIZE)]
    if best:
        blocks.append(_block("bestsellers", locale, await catalog.product_cards(db, best, locale)))
    categories = await catalog.list_categories(db, locale)
    brands = [b for b in await catalog.list_brands(db) if b.product_count > 0]
    brands.sort(key=lambda b: -b.product_count)
    return HomeOut(categories=categories, brands=brands, blocks=[b for b in blocks if b.items])


async def for_product(db: AsyncSession, product_id: uuid.UUID, locale: str) -> list[Block]:
    """Product page: "people also viewed" and "similar" (same category, then brand)."""
    cards = await catalog.product_cards(db, [product_id], locale)
    if not cards:
        raise AppError(MODULE, "PRODUCT_NOT_FOUND", "Product not found", status=404)
    me = cards[0]
    also = await catalog.product_cards(db, await engagement.also_viewed(db, product_id), locale)
    shown = {me.id} | {c.id for c in also}
    similar = [
        c
        for c in await _newest(
            db,
            locale,
            BLOCK_SIZE * 2,
            category=me.category.slug,
            brands=[me.brand.slug] if me.brand else [],
        )
        if c.id not in shown
    ]
    if len(similar) < BLOCK_SIZE:
        known = shown | {c.id for c in similar}
        similar += [
            c
            for c in await _newest(db, locale, BLOCK_SIZE * 2, category=me.category.slug)
            if c.id not in known
        ]
    blocks = [_block("also_viewed", locale, also), _block("similar", locale, similar[:BLOCK_SIZE])]
    return [b for b in blocks if b.items]
