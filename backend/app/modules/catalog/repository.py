"""Database queries of the `catalog` module. No business rules here, only data access."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.catalog.models import Brand, Category, Product, ProductImage, ProductVariant

Sort = Literal["newest", "price_asc", "price_desc", "popular", "rating"]


@dataclass
class ProductFilter:
    category_ids: Sequence[uuid.UUID] | None = None
    brand_slugs: Sequence[str] = field(default_factory=list)
    store_id: uuid.UUID | None = None
    q: str | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    in_stock: bool | None = None
    rating_min: Decimal | None = None
    sizes: Sequence[str] = field(default_factory=list)


# ---------------------------------------------------------------- categories and brands


async def all_categories(db: AsyncSession) -> Sequence[Category]:
    return (await db.scalars(select(Category).order_by(Category.position, Category.slug))).all()


async def get_category(db: AsyncSession, category_id: uuid.UUID) -> Category | None:
    return await db.get(Category, category_id)


async def get_category_by_slug(db: AsyncSession, slug: str) -> Category | None:
    return await db.scalar(select(Category).where(Category.slug == slug))


async def all_brands(db: AsyncSession, only_active: bool) -> Sequence[Brand]:
    stmt = select(Brand).order_by(Brand.name)
    if only_active:
        stmt = stmt.where(Brand.is_active.is_(True))
    return list((await db.scalars(stmt)).all())


async def get_brand(db: AsyncSession, brand_id: uuid.UUID) -> Brand | None:
    return await db.get(Brand, brand_id)


async def brands_by_ids(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, Brand]:
    if not ids:
        return {}
    return {b.id: b for b in await db.scalars(select(Brand).where(Brand.id.in_(ids)))}


# ---------------------------------------------------------------- listing


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conditions(
    visible: ColumnElement[bool], f: ProductFilter, *, skip_brand: bool = False
) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = [visible]
    if f.category_ids is not None:
        conds.append(Product.category_id.in_(f.category_ids))
    if f.brand_slugs and not skip_brand:
        conds.append(Product.brand_id.in_(select(Brand.id).where(Brand.slug.in_(f.brand_slugs))))
    if f.store_id is not None:
        conds.append(Product.store_id == f.store_id)
    if f.q:
        pattern = f"%{_escape_like(f.q)}%"
        conds.append(
            or_(
                Product.title.ilike(pattern, escape="\\"),
                Product.brand_id.in_(
                    select(Brand.id).where(Brand.name.ilike(pattern, escape="\\"))
                ),
            )
        )
    if f.price_min is not None:
        conds.append(Product.min_price >= f.price_min)
    if f.price_max is not None:
        conds.append(Product.min_price <= f.price_max)
    if f.in_stock is not None:
        conds.append(Product.in_stock.is_(f.in_stock))
    if f.rating_min is not None:
        conds.append(Product.rating_avg >= f.rating_min)
    if f.sizes:
        # "Size 42 in stock" means that very variant is in stock, not some other size.
        size_match = select(ProductVariant.id).where(
            ProductVariant.product_id == Product.id,
            ProductVariant.is_active.is_(True),
            ProductVariant.attributes["size"].astext.in_(f.sizes),
        )
        if f.in_stock:
            size_match = size_match.where(ProductVariant.in_stock.is_(True))
        conds.append(size_match.exists())
    return conds


def cover_url() -> Any:
    return (
        select(ProductImage.url)
        .where(
            ProductImage.product_id == Product.id,
            ProductImage.source == "seller",
            ProductImage.status == "approved",
        )
        .order_by(ProductImage.position, ProductImage.created_at)
        .limit(1)
        .correlate(Product)
        .scalar_subquery()
    )


def cheapest_compare_at() -> Any:
    return (
        select(ProductVariant.compare_at_price)
        .where(ProductVariant.product_id == Product.id, ProductVariant.is_active.is_(True))
        .order_by(ProductVariant.price)
        .limit(1)
        .correlate(Product)
        .scalar_subquery()
    )


_ORDER: dict[str, tuple[Any, ...]] = {
    "newest": (Product.published_at.desc().nulls_last(), Product.id.desc()),
    "price_asc": (Product.min_price.asc().nulls_last(), Product.id),
    "price_desc": (Product.min_price.desc().nulls_last(), Product.id),
    "popular": (Product.rating_count.desc(), Product.id.desc()),
    "rating": (Product.rating_avg.desc(), Product.rating_count.desc(), Product.id.desc()),
}


async def list_products(
    db: AsyncSession,
    visible: ColumnElement[bool],
    f: ProductFilter,
    sort: Sort,
    offset: int,
    limit: int,
) -> Sequence[tuple[Product, str | None, Decimal | None]]:
    stmt = (
        select(Product, cover_url(), cheapest_compare_at())
        .where(and_(*_conditions(visible, f)))
        .order_by(*_ORDER[sort])
        .offset(offset)
        .limit(limit)
    )
    return [(p, c, d) for p, c, d in (await db.execute(stmt)).all()]


async def count_by_category(db: AsyncSession, visible: ColumnElement[bool]) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(Product.category_id, func.count()).where(visible).group_by(Product.category_id)
    )
    return {cid: n for cid, n in rows.all()}


async def count_by_brand(
    db: AsyncSession, visible: ColumnElement[bool], f: ProductFilter
) -> dict[uuid.UUID, int]:
    rows = await db.execute(
        select(Product.brand_id, func.count())
        .where(and_(*_conditions(visible, f, skip_brand=True)), Product.brand_id.is_not(None))
        .group_by(Product.brand_id)
    )
    return {bid: n for bid, n in rows.all() if bid is not None}


async def price_range(
    db: AsyncSession, visible: ColumnElement[bool], f: ProductFilter
) -> tuple[Decimal | None, Decimal | None]:
    row = (
        await db.execute(
            select(func.min(Product.min_price), func.max(Product.min_price)).where(
                and_(*_conditions(visible, f))
            )
        )
    ).one()
    return row[0], row[1]


async def sizes(db: AsyncSession, visible: ColumnElement[bool], f: ProductFilter) -> list[str]:
    size = ProductVariant.attributes["size"].astext
    rows = await db.scalars(
        select(size)
        .distinct()
        .join(Product, Product.id == ProductVariant.product_id)
        .where(
            and_(*_conditions(visible, f)), ProductVariant.is_active.is_(True), size.is_not(None)
        )
    )
    return [s for s in rows.all() if s]


# ---------------------------------------------------------------- one product


def product_query() -> Select[Any]:
    return select(Product).where(Product.deleted_at.is_(None))


async def find_product(db: AsyncSession, *conds: ColumnElement[bool]) -> Product | None:
    found: Product | None = await db.scalar(product_query().where(*conds))
    return found


async def slug_taken(db: AsyncSession, slug: str) -> bool:
    return bool(await db.scalar(select(func.count()).where(Product.slug == slug)))


async def sku_taken(db: AsyncSession, skus: Sequence[str]) -> list[str]:
    if not skus:
        return []
    return list(
        (await db.scalars(select(ProductVariant.sku).where(ProductVariant.sku.in_(skus)))).all()
    )


async def variants_of(db: AsyncSession, product_id: uuid.UUID) -> Sequence[ProductVariant]:
    return (
        await db.scalars(
            select(ProductVariant)
            .where(ProductVariant.product_id == product_id)
            .order_by(ProductVariant.position, ProductVariant.price, ProductVariant.sku)
        )
    ).all()


async def images_of(db: AsyncSession, product_id: uuid.UUID) -> Sequence[ProductImage]:
    return (
        await db.scalars(
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.position, ProductImage.created_at)
        )
    ).all()


async def count_buyer_photos(db: AsyncSession, product_id: uuid.UUID, user_id: uuid.UUID) -> int:
    return int(
        await db.scalar(
            select(func.count()).where(
                ProductImage.product_id == product_id,
                ProductImage.source == "buyer",
                ProductImage.author_id == user_id,
            )
        )
        or 0
    )


async def get_variant(
    db: AsyncSession, product_id: uuid.UUID, variant_id: uuid.UUID
) -> ProductVariant | None:
    return await db.scalar(
        select(ProductVariant).where(
            ProductVariant.id == variant_id, ProductVariant.product_id == product_id
        )
    )


async def get_image(db: AsyncSession, image_id: uuid.UUID) -> ProductImage | None:
    return await db.get(ProductImage, image_id)


async def store_products(
    db: AsyncSession, store_id: uuid.UUID, status: str | None, offset: int, limit: int
) -> Sequence[Product]:
    stmt = product_query().where(Product.store_id == store_id)
    if status:
        stmt = stmt.where(Product.status == status)
    stmt = stmt.order_by(Product.created_at.desc(), Product.id.desc()).offset(offset).limit(limit)
    return (await db.scalars(stmt)).all()


async def store_variants(
    db: AsyncSession, store_id: uuid.UUID, variant_id: uuid.UUID | None = None
) -> Sequence[tuple[ProductVariant, Product]]:
    stmt = (
        select(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(Product.store_id == store_id, Product.deleted_at.is_(None))
        .order_by(Product.title, ProductVariant.position, ProductVariant.sku)
    )
    if variant_id is not None:
        stmt = stmt.where(ProductVariant.id == variant_id)
    return [(v, p) for v, p in (await db.execute(stmt)).all()]


async def variants_with_products(
    db: AsyncSession, variant_ids: Sequence[uuid.UUID]
) -> Sequence[tuple[ProductVariant, Product, str | None]]:
    rows = await db.execute(
        select(ProductVariant, Product, cover_url())
        .join(Product, Product.id == ProductVariant.product_id)
        .where(ProductVariant.id.in_(variant_ids))
    )
    return [(v, p, c) for v, p, c in rows.all()]


async def variant_id_by_sku(db: AsyncSession, sku: str) -> uuid.UUID | None:
    found: uuid.UUID | None = await db.scalar(
        select(ProductVariant.id).where(ProductVariant.sku == sku)
    )
    return found
