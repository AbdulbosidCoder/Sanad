"""Database queries of the `i18n` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.i18n.models import ProductTranslation, TranslationJob


async def translations_of(
    db: AsyncSession, product_ids: Sequence[uuid.UUID], locale: str | None = None
) -> Sequence[ProductTranslation]:
    stmt = select(ProductTranslation).where(ProductTranslation.product_id.in_(product_ids))
    if locale:
        stmt = stmt.where(ProductTranslation.locale == locale)
    return (await db.scalars(stmt)).all()


async def get_translation(
    db: AsyncSession, product_id: uuid.UUID, locale: str
) -> ProductTranslation | None:
    return await db.scalar(
        select(ProductTranslation).where(
            ProductTranslation.product_id == product_id, ProductTranslation.locale == locale
        )
    )


async def pending_job(
    db: AsyncSession, product_id: uuid.UUID, locale: str
) -> TranslationJob | None:
    return await db.scalar(
        select(TranslationJob).where(
            TranslationJob.product_id == product_id,
            TranslationJob.locale == locale,
            TranslationJob.status == "pending",
        )
    )


async def pending_jobs(db: AsyncSession, limit: int) -> Sequence[TranslationJob]:
    """Oldest pending jobs, locked; parallel workers skip each other's rows."""
    return (
        await db.scalars(
            select(TranslationJob)
            .where(TranslationJob.status == "pending")
            .order_by(TranslationJob.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    ).all()


async def pending_locales(db: AsyncSession, product_id: uuid.UUID) -> set[str]:
    rows = await db.scalars(
        select(TranslationJob.locale).where(
            TranslationJob.product_id == product_id, TranslationJob.status == "pending"
        )
    )
    return set(rows.all())


async def job_counts(db: AsyncSession) -> dict[str, int]:
    rows = await db.execute(
        select(TranslationJob.status, func.count()).group_by(TranslationJob.status)
    )
    return {s: int(n) for s, n in rows.all()}


async def retry_failed(db: AsyncSession) -> int:
    result = await db.execute(
        update(TranslationJob)
        .where(TranslationJob.status == "failed")
        .values(status="pending", attempts=0, last_error=None)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
