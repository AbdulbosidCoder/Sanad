"""Business logic of the `engagement` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import AppError
from app.core.events import publish
from app.core.pagination import Page, next_cursor
from app.core.security import hash_token
from app.modules.catalog import service as catalog
from app.modules.catalog.service import ProductCard
from app.modules.engagement import repository as repo
from app.modules.engagement.events import ProductViewed
from app.modules.engagement.schemas import FavoriteState, ViewOut

MODULE = "engagement"
VIEW_WINDOW = timedelta(minutes=30)


def _not_found() -> AppError:
    return AppError(MODULE, "PRODUCT_NOT_FOUND", "Product not found", status=404)


async def _card(db: AsyncSession, product_id: uuid.UUID) -> ProductCard:
    cards = await catalog.product_cards(db, [product_id], "ru")
    if not cards:
        raise _not_found()
    return cards[0]


# ---------------------------------------------------------------- favourites


async def add_favorite(
    db: AsyncSession, principal: Principal, product_id: uuid.UUID
) -> FavoriteState:
    await _card(db, product_id)  # only products a buyer can see
    await repo.add_favorite(db, principal.user_id, product_id)
    await db.commit()
    return FavoriteState(product_id=product_id, favorite=True)


async def remove_favorite(
    db: AsyncSession, principal: Principal, product_id: uuid.UUID
) -> FavoriteState:
    await repo.remove_favorite(db, principal.user_id, product_id)
    await db.commit()
    return FavoriteState(product_id=product_id, favorite=False)


async def favorites(
    db: AsyncSession, principal: Principal, locale: str, offset: int, limit: int
) -> Page[ProductCard]:
    ids = await repo.favorite_ids(db, principal.user_id, offset, limit + 1)
    cards = await catalog.product_cards(db, ids[:limit], locale)
    return Page(items=cards, next_cursor=next_cursor(offset, limit, len(ids)))


async def favorite_flags(
    db: AsyncSession, principal: Principal, product_ids: list[uuid.UUID]
) -> list[FavoriteState]:
    """Hearts for a list of cards in one request."""
    mine = await repo.favorites_among(db, principal.user_id, product_ids)
    return [FavoriteState(product_id=p, favorite=p in mine) for p in product_ids]


async def favorite_counts(db: AsyncSession, product_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    return await repo.favorite_counts(db, product_ids)


async def favorite_product_ids(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 50
) -> list[uuid.UUID]:
    return await repo.favorite_ids(db, user_id, 0, limit)


# ---------------------------------------------------------------- views


def viewer_key(principal: Principal | None, device_id: str | None, client_ip: str | None) -> str:
    if principal is not None:
        return f"u:{principal.user_id}"
    return hash_token(f"d:{device_id}" if device_id else f"ip:{client_ip or '-'}")


async def record_view(
    db: AsyncSession, principal: Principal | None, product_id: uuid.UUID, viewer: str
) -> ViewOut:
    card = await _card(db, product_id)
    since = datetime.now(UTC) - VIEW_WINDOW
    if await repo.recent_view_exists(db, viewer, product_id, since):
        return ViewOut(counted=False)
    user_id = principal.user_id if principal else None
    repo.add_view(db, product_id, card.store.id, user_id, viewer)
    await publish(db, ProductViewed(product_id, card.store.id, user_id))
    await db.commit()
    return ViewOut(counted=True)


async def recently_viewed(
    db: AsyncSession, principal: Principal, locale: str, limit: int = 20
) -> list[ProductCard]:
    return await catalog.product_cards(
        db, await repo.recently_viewed(db, principal.user_id, limit), locale
    )


async def recently_viewed_ids(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 20
) -> list[uuid.UUID]:
    return await repo.recently_viewed(db, user_id, limit)


async def most_viewed(
    db: AsyncSession, days: int, limit: int, store_id: uuid.UUID | None = None
) -> list[tuple[uuid.UUID, int]]:
    """(product_id, views) over the last ``days`` — trends, store analytics."""
    return await repo.most_viewed(db, datetime.now(UTC) - timedelta(days=days), limit, store_id)


async def store_views(
    db: AsyncSession, store_id: uuid.UUID, since: datetime, until: datetime
) -> tuple[int, int]:
    return await repo.store_views(db, store_id, since, until)


async def views_by_product(
    db: AsyncSession, product_ids: list[uuid.UUID], since: datetime
) -> dict[uuid.UUID, int]:
    return await repo.views_by_product(db, product_ids, since) if product_ids else {}


async def also_viewed(db: AsyncSession, product_id: uuid.UUID, limit: int = 12) -> list[uuid.UUID]:
    """Products opened by the people who opened this one (last 30 days)."""
    since = datetime.now(UTC) - timedelta(days=30)
    viewers = await repo.viewers_of(db, product_id, since, 500)
    return await repo.also_viewed(db, product_id, viewers, since, limit) if viewers else []
