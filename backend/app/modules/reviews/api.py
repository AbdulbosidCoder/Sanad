"""HTTP endpoints of the `reviews` module. Business logic lives in service.py."""

import uuid
from typing import Literal

from fastapi import Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_optional_principal, get_principal, require_permission
from app.core.db import get_session
from app.core.modules import module_router
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, decode_cursor
from app.modules.reviews import service
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
from app.modules.stores.service import StoreAccess, store_access

router = module_router("reviews")
Limit = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


def _offset(cursor: str | None) -> int:
    return decode_cursor(cursor, "reviews")


@router.get("/products/{product_id}/reviews")
async def reviews(
    product_id: uuid.UUID,
    rating: int | None = Query(None, ge=1, le=5),
    sort: Literal["newest", "rating_desc", "rating_asc"] = "newest",
    cursor: str | None = None,
    limit: int = Limit,
    db: AsyncSession = Depends(get_session),
) -> Page[ReviewOut]:
    return await service.list_reviews(db, product_id, rating, sort, _offset(cursor), limit)


@router.get("/products/{product_id}/reviews/summary")
async def summary(product_id: uuid.UUID, db: AsyncSession = Depends(get_session)) -> Summary:
    """Average, stars distribution and how the size fits."""
    return await service.summary(db, product_id)


@router.get("/products/{product_id}/reviews/can-review")
async def can_review(
    product_id: uuid.UUID,
    principal: Principal | None = Depends(get_optional_principal),
    db: AsyncSession = Depends(get_session),
) -> CanReview:
    return await service.can_review(db, principal, product_id)


@router.post("/products/{product_id}/reviews", status_code=201)
async def create(
    product_id: uuid.UUID,
    data: ReviewIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> ReviewOut:
    """Only after the product was delivered to you. Photos: POST /products/{slug}/buyer-photos."""
    return await service.create(db, principal, product_id, data)


@router.get("/me/reviews")
async def mine(
    principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_session)
) -> list[ModerationOut]:
    return await service.my_reviews(db, principal)


@router.patch("/me/reviews/{review_id}")
async def update(
    review_id: uuid.UUID,
    data: ReviewUpdate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> ReviewOut:
    return await service.update(db, principal, review_id, data)


@router.delete("/me/reviews/{review_id}", status_code=204)
async def delete(
    review_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await service.delete(db, principal, review_id)
    return Response(status_code=204)


@router.get("/seller/reviews")
async def store_reviews(
    unanswered: bool = False,
    cursor: str | None = None,
    limit: int = Limit,
    access: StoreAccess = Depends(store_access()),
    db: AsyncSession = Depends(get_session),
) -> Page[ReviewOut]:
    return await service.store_reviews(db, access, unanswered, _offset(cursor), limit)


@router.put("/seller/reviews/{review_id}/reply")
async def reply(
    review_id: uuid.UUID,
    data: ReplyIn,
    access: StoreAccess = Depends(store_access("products.write")),
    db: AsyncSession = Depends(get_session),
) -> ReviewOut:
    return await service.reply(db, access, review_id, data)


@router.get("/admin/reviews")
async def moderation(
    status: Literal["published", "hidden"] | None = None,
    max_rating: int | None = Query(None, ge=1, le=5, description="e.g. 2 = only 1-2 stars"),
    cursor: str | None = None,
    limit: int = Limit,
    _: Principal = Depends(require_permission("reviews.hide")),
    db: AsyncSession = Depends(get_session),
) -> list[ModerationOut]:
    return await service.moderation_list(db, status, max_rating, _offset(cursor), limit)


@router.post("/admin/reviews/{review_id}/hide")
async def hide(
    review_id: uuid.UUID,
    data: HideIn,
    actor: Principal = Depends(require_permission("reviews.hide")),
    db: AsyncSession = Depends(get_session),
) -> ModerationOut:
    return await service.set_hidden(db, actor, review_id, data)


@router.post("/admin/reviews/{review_id}/unhide")
async def unhide(
    review_id: uuid.UUID,
    actor: Principal = Depends(require_permission("reviews.hide")),
    db: AsyncSession = Depends(get_session),
) -> ModerationOut:
    return await service.set_hidden(db, actor, review_id, None)
