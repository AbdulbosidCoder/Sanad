"""Database queries of the `search` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, false, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.search.models import SearchDocument, SearchHistory


async def upsert_document(db: AsyncSession, product_id: uuid.UUID, document: str) -> None:
    stmt = insert(SearchDocument).values(product_id=product_id, document=document)
    stmt = stmt.on_conflict_do_update(
        index_elements=[SearchDocument.product_id],
        set_={"document": stmt.excluded.document, "updated_at": func.now()},
    )
    await db.execute(stmt)


async def delete_document(db: AsyncSession, product_id: uuid.UUID) -> None:
    await db.execute(delete(SearchDocument).where(SearchDocument.product_id == product_id))


def match(tokens: Sequence[str], text: str) -> Any:
    """Subquery (product_id, rank): word-prefix full-text match OR a close trigram match."""
    if not tokens:
        return (
            select(SearchDocument.product_id, literal(0.0).label("rank")).where(false()).subquery()
        )
    query = func.to_tsquery("simple", " & ".join(f"{t}:*" for t in tokens))
    similarity = func.word_similarity(text, SearchDocument.document)
    return (
        select(
            SearchDocument.product_id,
            (func.ts_rank(SearchDocument.tsv, query) + similarity).label("rank"),
        )
        .where(
            or_(
                SearchDocument.tsv.op("@@")(query),
                literal(text).op("<%")(SearchDocument.document),  # typo-tolerant, uses the index
            )
        )
        .subquery()
    )


async def matching_ids(
    db: AsyncSession, tokens: Sequence[str], text: str, limit: int
) -> list[uuid.UUID]:
    m = match(tokens, text)
    rows = await db.scalars(select(m.c.product_id).order_by(m.c.rank.desc()).limit(limit))
    return list(rows.all())


async def remember(db: AsyncSession, user_id: uuid.UUID, query: str) -> None:
    stmt = insert(SearchHistory).values(user_id=user_id, query=query)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_search_history_query", set_={"searched_at": func.now()}
    )
    await db.execute(stmt)


async def history(
    db: AsyncSession, user_id: uuid.UUID, prefix: str, limit: int
) -> Sequence[SearchHistory]:
    stmt = select(SearchHistory).where(SearchHistory.user_id == user_id)
    if prefix:
        stmt = stmt.where(SearchHistory.query.startswith(prefix, autoescape=True))
    return (await db.scalars(stmt.order_by(SearchHistory.searched_at.desc()).limit(limit))).all()


async def forget(db: AsyncSession, user_id: uuid.UUID, query: str | None) -> None:
    stmt = delete(SearchHistory).where(SearchHistory.user_id == user_id)
    if query is not None:
        stmt = stmt.where(SearchHistory.query == query)
    await db.execute(stmt)


async def popular(db: AsyncSession, since: datetime, limit: int) -> list[tuple[str, int]]:
    rows = await db.execute(
        select(SearchHistory.query, func.count().label("n"))
        .where(SearchHistory.searched_at >= since)
        .group_by(SearchHistory.query)
        .order_by(func.count().desc(), SearchHistory.query)
        .limit(limit)
    )
    return [(q, n) for q, n in rows.all()]


async def document_count(db: AsyncSession) -> int:
    return int(await db.scalar(select(func.count()).select_from(SearchDocument)) or 0)
