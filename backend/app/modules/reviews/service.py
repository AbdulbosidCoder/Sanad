"""Business logic of the `reviews` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

Rules: only a buyer who received the product reviews it (``orders.purchased_item``), one
review per buyer and product, editable by its author. The store may answer once (and edit
the answer). Platform staff with ``reviews.hide`` hide abusive reviews. The product's
``rating_avg`` / ``rating_count`` in the catalog are recalculated after every change.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import AppError
from app.core.events import publish
from app.core.models import uuid7
from app.core.pagination import Page, next_cursor
from app.modules.audit import service as audit
from app.modules.catalog import service as catalog
from app.modules.identity import service as identity
from app.modules.orders import service as orders
from app.modules.reviews import repository as repo
from app.modules.reviews.events import ReviewPublished
from app.modules.reviews.models import Review
from app.modules.reviews.schemas import (
    CanReview,
    HideIn,
    ModerationOut,
    ReplyIn,
    ReviewIn,
    ReviewOut,
    ReviewUpdate,
    Summary,
)
from app.modules.stores.service import StoreAccess

MODULE = "reviews"


def _error(code: str, detail: str, status: int) -> AppError:
    return AppError(MODULE, code, detail, status=status)


def _short_name(full_name: str) -> str:
    parts = full_name.split()
    if not parts:
        return "Покупатель"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[1][0]}."


async def _authors(db: AsyncSession, reviews: Sequence[Review]) -> dict[uuid.UUID, str]:
    out: dict[uuid.UUID, str] = {}
    for r in reviews:
        if r.user_id not in out:
            brief = await identity.user_brief(db, r.user_id)
            out[r.user_id] = _short_name(brief[1] if brief else "")
    return out


async def _out(db: AsyncSession, reviews: Sequence[Review]) -> list[ReviewOut]:
    names = await _authors(db, reviews)
    return [
        ReviewOut(
            id=r.id,
            product_id=r.product_id,
            rating=r.rating,
            text=r.text,
            fit=r.fit,
            author=names[r.user_id],
            seller_reply=r.seller_reply,
            replied_at=r.replied_at,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in reviews
    ]


async def _refresh_rating(db: AsyncSession, product_id: uuid.UUID) -> None:
    avg, count = await repo.stats(db, product_id)
    await catalog.set_rating(db, product_id, avg, count)


# ---------------------------------------------------------------- public


async def list_reviews(
    db: AsyncSession, product_id: uuid.UUID, rating: int | None, sort: str, offset: int, limit: int
) -> Page[ReviewOut]:
    rows = await repo.published(db, product_id, rating, sort, offset, limit + 1)
    return Page(
        items=await _out(db, rows[:limit]), next_cursor=next_cursor(offset, limit, len(rows))
    )


async def summary(db: AsyncSession, product_id: uuid.UUID) -> Summary:
    avg, count = await repo.stats(db, product_id)
    dist = await repo.distribution(db, product_id)
    return Summary(
        rating_avg=avg,
        rating_count=count,
        distribution={s: dist.get(s, 0) for s in range(5, 0, -1)},
        fit=await repo.fits(db, product_id),
    )


async def can_review(
    db: AsyncSession, principal: Principal | None, product_id: uuid.UUID
) -> CanReview:
    if principal is None:
        return CanReview(can_review=False, reason="sign_in")
    existing = await repo.of_user(db, principal.user_id, product_id)
    if existing is not None:
        return CanReview(can_review=False, reason="already_reviewed", review_id=existing.id)
    if await orders.purchased_item(db, principal.user_id, product_id) is None:
        return CanReview(can_review=False, reason="not_purchased")
    return CanReview(can_review=True, reason="ok")


# ---------------------------------------------------------------- buyer


async def create(
    db: AsyncSession, principal: Principal, product_id: uuid.UUID, data: ReviewIn
) -> ReviewOut:
    item_id = await orders.purchased_item(db, principal.user_id, product_id)
    if item_id is None:
        raise _error("NOT_PURCHASED", "Only buyers who received the product can review it", 403)
    store_id = await catalog.product_store(db, product_id)
    if store_id is None:
        raise _error("PRODUCT_NOT_FOUND", "Product not found", 404)
    review = Review(
        id=uuid7(),
        product_id=product_id,
        store_id=store_id,
        user_id=principal.user_id,
        order_item_id=item_id,
        rating=data.rating,
        text=data.text,
        fit=data.fit,
    )
    db.add(review)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise _error("ALREADY_REVIEWED", "You already reviewed this product", 409) from exc
    await _refresh_rating(db, product_id)
    await publish(db, ReviewPublished(review.id, product_id, store_id, review.rating))
    await db.commit()
    return (await _out(db, [review]))[0]


async def _mine(db: AsyncSession, principal: Principal, review_id: uuid.UUID) -> Review:
    review = await repo.get(db, review_id)
    if review is None or review.user_id != principal.user_id:
        raise _error("NOT_FOUND", "Review not found", 404)
    return review


async def update(
    db: AsyncSession, principal: Principal, review_id: uuid.UUID, data: ReviewUpdate
) -> ReviewOut:
    review = await _mine(db, principal, review_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None or field == "fit":
            setattr(review, field, value)
    await db.flush()
    await _refresh_rating(db, review.product_id)
    if review.status == "published":
        await publish(
            db, ReviewPublished(review.id, review.product_id, review.store_id, review.rating)
        )
    await db.commit()
    await db.refresh(review)
    return (await _out(db, [review]))[0]


async def delete(db: AsyncSession, principal: Principal, review_id: uuid.UUID) -> None:
    review = await _mine(db, principal, review_id)
    product_id = review.product_id
    await db.delete(review)
    await db.flush()
    await _refresh_rating(db, product_id)
    await db.commit()


async def my_reviews(db: AsyncSession, principal: Principal) -> list[ModerationOut]:
    rows = await repo.of_author(db, principal.user_id)
    return await _moderation_out(db, rows)


# ---------------------------------------------------------------- seller


async def store_reviews(
    db: AsyncSession, access: StoreAccess, unanswered: bool, offset: int, limit: int
) -> Page[ReviewOut]:
    rows = await repo.of_store(db, access.store_id, unanswered, offset, limit + 1)
    return Page(
        items=await _out(db, rows[:limit]), next_cursor=next_cursor(offset, limit, len(rows))
    )


async def reply(
    db: AsyncSession, access: StoreAccess, review_id: uuid.UUID, data: ReplyIn
) -> ReviewOut:
    review = await repo.get(db, review_id)
    if review is None or review.store_id != access.store_id or review.status != "published":
        raise _error("NOT_FOUND", "Review not found", 404)
    review.seller_reply = data.text
    review.replied_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(review)
    return (await _out(db, [review]))[0]


async def store_rating(db: AsyncSession, store_id: uuid.UUID) -> tuple[float, int]:
    avg, count = await repo.store_rating(db, store_id)
    return float(avg), count


# ---------------------------------------------------------------- moderation


async def _moderation_out(db: AsyncSession, rows: Sequence[Review]) -> list[ModerationOut]:
    public = {r.id: r for r in await _out(db, rows)}
    return [
        ModerationOut(
            **public[r.id].model_dump(),
            status=r.status,
            hidden_reason=r.hidden_reason,
            user_id=r.user_id,
        )
        for r in rows
    ]


async def moderation_list(
    db: AsyncSession, status: str | None, max_rating: int | None, offset: int, limit: int
) -> list[ModerationOut]:
    return await _moderation_out(db, await repo.all_reviews(db, status, max_rating, offset, limit))


async def set_hidden(
    db: AsyncSession, actor: Principal, review_id: uuid.UUID, hide: HideIn | None
) -> ModerationOut:
    review = await repo.get(db, review_id)
    if review is None:
        raise _error("NOT_FOUND", "Review not found", 404)
    review.status = "hidden" if hide else "published"
    review.hidden_reason = hide.reason if hide else None
    await audit.record(
        db,
        actor.user_id,
        "reviews.hide" if hide else "reviews.unhide",
        "review",
        review.id,
        {"reason": hide.reason if hide else None},
    )
    await db.flush()
    await _refresh_rating(db, review.product_id)
    await db.commit()
    await db.refresh(review)
    return (await _moderation_out(db, [review]))[0]
