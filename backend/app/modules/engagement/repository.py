"""Database queries of the `engagement` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import uuid7
from app.modules.engagement.models import Favorite, ProductView


async def add_favorite(db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID) -> None:
    await db.execute(
        insert(Favorite)
        .values(id=uuid7(), user_id=user_id, product_id=product_id)
        .on_conflict_do_nothing(constraint="uq_favorites_user_product")
    )


async def remove_favorite(db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID) -> None:
    await db.execute(
        delete(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
    )


async def favorite_ids(
    db: AsyncSession, user_id: uuid.UUID, offset: int = 0, limit: int = 1000
) -> list[uuid.UUID]:
    rows = await db.scalars(
        select(Favorite.product_id)
        .where(Favorite.user_id == user_id)
        .order_by(Favorite.created_at.desc(), Favorite.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(rows.all())


async def favorites_among(
    db: AsyncSession, user_id: uuid.UUID, product_ids: Sequence[uuid.UUID]
) -> set[uuid.UUID]:
    rows = await db.scalars(
        select(Favorite.product_id).where(
            Favorite.user_id == user_id, Favorite.product_id.in_(product_ids)
        )
    )
    return set(rows.all())


async def favorite_counts(
    db: AsyncSession, product_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(Favorite.product_id, func.count())
        .where(Favorite.product_id.in_(product_ids))
        .group_by(Favorite.product_id)
    )
    return {p: n for p, n in rows.all()}


async def recent_view_exists(
    db: AsyncSession, viewer: str, product_id: uuid.UUID, since: datetime
) -> bool:
    found = await db.scalar(
        select(ProductView.id)
        .where(
            ProductView.viewer == viewer,
            ProductView.product_id == product_id,
            ProductView.viewed_at >= since,
        )
        .limit(1)
    )
    return found is not None


async def recently_viewed(db: AsyncSession, user_id: uuid.UUID, limit: int) -> list[uuid.UUID]:
    last = func.max(ProductView.viewed_at)
    rows = await db.scalars(
        select(ProductView.product_id)
        .where(ProductView.user_id == user_id)
        .group_by(ProductView.product_id)
        .order_by(last.desc())
        .limit(limit)
    )
    return list(rows.all())


async def most_viewed(
    db: AsyncSession, since: datetime, limit: int, store_id: uuid.UUID | None = None
) -> list[tuple[uuid.UUID, int]]:
    stmt = select(ProductView.product_id, func.count()).where(ProductView.viewed_at >= since)
    if store_id is not None:
        stmt = stmt.where(ProductView.store_id == store_id)
    rows = await db.execute(
        stmt.group_by(ProductView.product_id).order_by(func.count().desc()).limit(limit)
    )
    return [(p, n) for p, n in rows.all()]


async def store_views(
    db: AsyncSession, store_id: uuid.UUID, since: datetime, until: datetime
) -> tuple[int, int]:
    """(views, distinct viewers) of a store's products in a period."""
    row = (
        await db.execute(
            select(func.count(), func.count(func.distinct(ProductView.viewer))).where(
                ProductView.store_id == store_id,
                ProductView.viewed_at >= since,
                ProductView.viewed_at < until,
            )
        )
    ).one()
    return int(row[0]), int(row[1])


async def views_by_product(
    db: AsyncSession, product_ids: Sequence[uuid.UUID], since: datetime
) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(ProductView.product_id, func.count())
        .where(ProductView.product_id.in_(product_ids), ProductView.viewed_at >= since)
        .group_by(ProductView.product_id)
    )
    return {p: n for p, n in rows.all()}


async def viewers_of(
    db: AsyncSession, product_id: uuid.UUID, since: datetime, limit: int
) -> list[str]:
    rows = await db.scalars(
        select(ProductView.viewer)
        .where(ProductView.product_id == product_id, ProductView.viewed_at >= since)
        .distinct()
        .limit(limit)
    )
    return list(rows.all())


async def also_viewed(
    db: AsyncSession, product_id: uuid.UUID, viewers: Sequence[str], since: datetime, limit: int
) -> list[uuid.UUID]:
    rows = await db.scalars(
        select(ProductView.product_id)
        .where(
            ProductView.viewer.in_(viewers),
            ProductView.product_id != product_id,
            ProductView.viewed_at >= since,
        )
        .group_by(ProductView.product_id)
        .order_by(func.count(func.distinct(ProductView.viewer)).desc())
        .limit(limit)
    )
    return list(rows.all())


def add_view(
    db: AsyncSession,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    user_id: uuid.UUID | None,
    viewer: str,
) -> None:
    db.add(
        ProductView(
            id=uuid7(), product_id=product_id, store_id=store_id, user_id=user_id, viewer=viewer
        )
    )
