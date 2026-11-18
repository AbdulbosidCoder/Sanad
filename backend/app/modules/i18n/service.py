"""Business logic of the `i18n` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

Flow: catalog publishes ``ProductCreated`` / ``ProductUpdated`` -> a job per missing
language is queued in the same transaction -> the worker (``i18n.translate_pending``,
every minute) translates -> the catalog shows the translation in that language (it asks
through ``catalog.set_translation_lookup``, installed in ``setup``).
"""

import hashlib
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker
from app.core.errors import AppError
from app.core.events import publish, subscribe
from app.core.locale import LOCALES
from app.core.models import uuid7
from app.modules.catalog import service as catalog
from app.modules.catalog.events import ProductCreated, ProductUpdated
from app.modules.i18n import repository as repo
from app.modules.i18n.events import TranslationReady
from app.modules.i18n.models import ProductTranslation, TranslationJob
from app.modules.i18n.schemas import TranslationIn, TranslationOut
from app.modules.i18n.translators import TranslationUnavailable, get_translator
from app.modules.stores.service import StoreAccess

MODULE = "i18n"
MAX_ATTEMPTS = 5

logger = logging.getLogger("app.modules.i18n")


def _error(code: str, detail: str, status: int) -> AppError:
    return AppError(MODULE, code, detail, status=status)


def source_hash(title: str, description: str) -> str:
    return hashlib.sha256(f"{title}\n\x00\n{description}".encode()).hexdigest()


# ---------------------------------------------------------------- wiring


def setup() -> None:
    subscribe(ProductCreated, on_product_text_changed)
    subscribe(ProductUpdated, on_product_text_changed)
    catalog.set_translation_lookup(lookup)


async def lookup(
    db: AsyncSession, product_ids: Sequence[uuid.UUID], locale: str
) -> dict[uuid.UUID, tuple[str, str]]:
    """Installed into catalog: translated (title, description) per product."""
    return {
        t.product_id: (t.title, t.description)
        for t in await repo.translations_of(db, product_ids, locale)
    }


async def on_product_text_changed(db: AsyncSession, event: ProductCreated | ProductUpdated) -> None:
    for locale in LOCALES:
        if (
            locale != event.source_locale
            and await repo.pending_job(db, event.product_id, locale) is None
        ):
            db.add(TranslationJob(id=uuid7(), product_id=event.product_id, locale=locale))
    # A translation into what is now the original language is no longer needed.
    old = await repo.get_translation(db, event.product_id, event.source_locale)
    if old is not None:
        await db.delete(old)


# ---------------------------------------------------------------- background work


async def _run(db: AsyncSession, job: TranslationJob) -> None:
    source = await catalog.product_source(db, job.product_id)
    if source is None or source.source_locale == job.locale:
        return
    digest = source_hash(source.title, source.description)
    existing = await repo.get_translation(db, job.product_id, job.locale)
    if existing is not None and existing.origin == "manual":
        # Never overwrite the seller's own text; ask them to check it instead.
        existing.needs_review = existing.source_hash != digest
        return
    if existing is not None and existing.source_hash == digest:
        return
    translator = get_translator()
    title = await translator.translate(source.title, source.source_locale, job.locale, kind="title")
    description = await translator.translate(
        source.description, source.source_locale, job.locale, kind="description"
    )
    await save(db, job.product_id, job.locale, title, description, "machine", digest)


async def process_pending(db: AsyncSession, limit: int = 20) -> int:
    """Translates up to ``limit`` queued jobs. Returns how many finished."""
    done = 0
    for job in await repo.pending_jobs(db, limit):
        job.attempts += 1
        try:
            await _run(db, job)
        except TranslationUnavailable as exc:
            job.last_error = str(exc)[:500]
            if job.attempts >= MAX_ATTEMPTS:
                job.status = "failed"
            continue
        job.status = "done"
        job.finished_at = datetime.now(UTC)
        done += 1
    await db.commit()
    return done


async def translate_pending_job() -> int:
    """Entry point of the worker task."""
    async with get_sessionmaker()() as db:
        count = await process_pending(db)
    if count:
        logger.info("translations done", extra={"extra_fields": {"count": count}})
    return count


async def save(
    db: AsyncSession,
    product_id: uuid.UUID,
    locale: str,
    title: str,
    description: str,
    origin: str,
    digest: str | None = None,
) -> None:
    """Writes a translation (no commit). ``origin``: machine | manual."""
    if digest is None:
        source = await catalog.product_source(db, product_id)
        digest = source_hash(source.title, source.description) if source else ""
    row = await repo.get_translation(db, product_id, locale)
    if row is None:
        row = ProductTranslation(
            id=uuid7(),
            product_id=product_id,
            locale=locale,
            title=title,
            description=description,
            origin=origin,
            source_hash=digest,
        )
        db.add(row)
    else:
        row.title, row.description, row.origin = title, description, origin
        row.source_hash, row.needs_review = digest, False
    await db.flush()
    await publish(db, TranslationReady(product_id, locale))


async def put_translation(
    db: AsyncSession,
    product_id: uuid.UUID,
    locale: str,
    title: str,
    description: str,
    origin: str,
) -> None:
    """Saves a ready translation and closes its queued job (no commit). Used by demo data."""
    await save(db, product_id, locale, title, description, origin)
    job = await repo.pending_job(db, product_id, locale)
    if job is not None:
        job.status = "done"
        job.finished_at = datetime.now(UTC)


async def texts_of(db: AsyncSession, product_id: uuid.UUID) -> list[tuple[str, str, str]]:
    """(locale, title, description) of every translation of a product (search index)."""
    return [
        (t.locale, t.title, t.description) for t in await repo.translations_of(db, [product_id])
    ]


async def has_translations(db: AsyncSession, product_id: uuid.UUID) -> bool:
    return bool(await repo.translations_of(db, [product_id]))


# ---------------------------------------------------------------- seller API


async def _own(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID
) -> catalog.ProductSource:
    source = await catalog.product_source(db, product_id, access.store_id)
    if source is None:
        raise _error("PRODUCT_NOT_FOUND", "Product not found", 404)
    return source


async def product_translations(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID
) -> list[TranslationOut]:
    source = await _own(db, access, product_id)
    rows = {t.locale: t for t in await repo.translations_of(db, [product_id])}
    pending = await repo.pending_locales(db, product_id)
    out: list[TranslationOut] = []
    for locale in LOCALES:
        if locale == source.source_locale:
            out.append(
                TranslationOut(
                    locale=locale,
                    state="original",
                    title=source.title,
                    description=source.description,
                )
            )
        elif locale in rows:
            t = rows[locale]
            out.append(
                TranslationOut(
                    locale=locale,
                    state=t.origin,
                    title=t.title,
                    description=t.description,
                    needs_review=t.needs_review,
                    updated_at=t.updated_at,
                )
            )
        else:
            out.append(
                TranslationOut(
                    locale=locale,
                    state="pending" if locale in pending else "missing",
                    title=None,
                    description=None,
                )
            )
    return out


async def edit_translation(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID, locale: str, data: TranslationIn
) -> list[TranslationOut]:
    """The seller's own translation. Machine translation will not overwrite it."""
    source = await _own(db, access, product_id)
    if locale == source.source_locale:
        raise _error("IS_ORIGINAL", "This is the original language: edit the product itself", 409)
    await put_translation(db, product_id, locale, data.title, data.description, "manual")
    await db.commit()
    return await product_translations(db, access, product_id)


async def retranslate(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID, locale: str
) -> list[TranslationOut]:
    """Drop the seller's edit and queue a fresh machine translation."""
    source = await _own(db, access, product_id)
    if locale == source.source_locale:
        raise _error("IS_ORIGINAL", "This is the original language", 409)
    row = await repo.get_translation(db, product_id, locale)
    if row is not None:
        await db.delete(row)
    if await repo.pending_job(db, product_id, locale) is None:
        db.add(TranslationJob(id=uuid7(), product_id=product_id, locale=locale))
    await db.commit()
    return await product_translations(db, access, product_id)


async def job_counts(db: AsyncSession) -> dict[str, int]:
    """Translation jobs by status (ops dashboard)."""
    return await repo.job_counts(db)


async def retry_failed_jobs(db: AsyncSession) -> int:
    count = await repo.retry_failed(db)
    await db.commit()
    return count
