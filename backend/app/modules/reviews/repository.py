"""Database queries of the `reviews` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reviews.models import Review


async def get(db: AsyncSession, review_id: uuid.UUID) -> Review | None:
    return await db.get(Review, review_id)


async def of_user(db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID) -> Review | None:
    return await db.scalar(
        select(Review).where(Review.user_id == user_id, Review.product_id == product_id)
    )


async def published(
    db: AsyncSession, product_id: uuid.UUID, rating: int | None, sort: str, offset: int, limit: int
) -> Sequence[Review]:
    stmt = select(Review).where(Review.product_id == product_id, Review.status == "published")
    if rating is not None:
        stmt = stmt.where(Review.rating == rating)
    order = {
        "newest": (Review.created_at.desc(),),
        "rating_desc": (Review.rating.desc(), Review.created_at.desc()),
        "rating_asc": (Review.rating.asc(), Review.created_at.desc()),
    }[sort]
    return (
        await db.scalars(stmt.order_by(*order, Review.id.desc()).offset(offset).limit(limit))
    ).all()


async def stats(db: AsyncSession, product_id: uuid.UUID) -> tuple[Decimal, int]:
    row = (
        await db.execute(
            select(func.coalesce(func.avg(Review.rating), 0), func.count()).where(
                Review.product_id == product_id, Review.status == "published"
            )
        )
    ).one()
    return Decimal(row[0]).quantize(Decimal("0.01")), int(row[1])


async def distribution(db: AsyncSession, product_id: uuid.UUID) -> dict[int, int]:
    rows = await db.execute(
        select(Review.rating, func.count())
        .where(Review.product_id == product_id, Review.status == "published")
        .group_by(Review.rating)
    )
    return {int(r): int(n) for r, n in rows.all()}


async def fits(db: AsyncSession, product_id: uuid.UUID) -> dict[str, int]:
    rows = await db.execute(
        select(Review.fit, func.count())
        .where(
            Review.product_id == product_id, Review.status == "published", Review.fit.is_not(None)
        )
        .group_by(Review.fit)
    )
    return {str(f): int(n) for f, n in rows.all()}


async def of_store(
    db: AsyncSession, store_id: uuid.UUID, unanswered: bool, offset: int, limit: int
) -> Sequence[Review]:
    stmt = select(Review).where(Review.store_id == store_id, Review.status == "published")
    if unanswered:
        stmt = stmt.where(Review.seller_reply.is_(None))
    return (
        await db.scalars(stmt.order_by(Review.created_at.desc()).offset(offset).limit(limit))
    ).all()


async def all_reviews(
    db: AsyncSession, status: str | None, max_rating: int | None, offset: int, limit: int
) -> Sequence[Review]:
    stmt = select(Review)
    if status:
        stmt = stmt.where(Review.status == status)
    if max_rating is not None:
        stmt = stmt.where(Review.rating <= max_rating)
    return (
        await db.scalars(stmt.order_by(Review.created_at.desc()).offset(offset).limit(limit))
    ).all()


async def store_rating(db: AsyncSession, store_id: uuid.UUID) -> tuple[Decimal, int]:
    row = (
        await db.execute(
            select(func.coalesce(func.avg(Review.rating), 0), func.count()).where(
                Review.store_id == store_id, Review.status == "published"
            )
        )
    ).one()
    return Decimal(row[0]).quantize(Decimal("0.01")), int(row[1])


async def of_author(db: AsyncSession, user_id: uuid.UUID) -> Sequence[Review]:
    return (
        await db.scalars(
            select(Review).where(Review.user_id == user_id).order_by(Review.created_at.desc())
        )
    ).all()
