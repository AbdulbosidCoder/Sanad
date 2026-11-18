"""Business logic of the `catalog` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

Who sees what:
- buyers see products that are ``active``, not deleted, in an *active* store;
- sellers see and change only products of the store in ``X-Store-Id`` (others answer 404);
- admins manage categories and brands and can block any product.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import AppError
from app.core.events import publish as publish_event
from app.core.locale import pick
from app.core.models import uuid7
from app.core.pagination import Page, next_cursor
from app.core.text import unique_slug
from app.modules.catalog import repository as repo
from app.modules.catalog.events import ProductArchived, ProductCreated, ProductUpdated
from app.modules.catalog.models import (
    PHOTO_ANGLES,
    Brand,
    Category,
    Product,
    ProductImage,
    ProductVariant,
)
from app.modules.catalog.repository import ProductFilter
from app.modules.catalog.repository import Sort as Sort  # re-exported for search
from app.modules.catalog.schemas import (
    BrandAdminOut,
    BrandIn,
    BrandUpdate,
    CategoryAdminOut,
    CategoryIn,
    CategoryUpdate,
    FiltersOut,
    ImageIn,
    ImageOut,
    ModerateIn,
    PhotoCoverage,
    PriceRange,
    ProductDetail,
    ProductIn,
    ProductUpdate,
    RefOut,
    SellerProductOut,
    VariantIn,
    VariantOut,
    VariantUpdate,
)
from app.modules.catalog.schemas import BrandOut as BrandOut
from app.modules.catalog.schemas import CategoryOut as CategoryOut
from app.modules.catalog.schemas import ProductCard as ProductCard
from app.modules.stores import service as stores
from app.modules.stores.service import StoreAccess

MODULE = "catalog"
MAX_IMAGES = 30
MAX_BUYER_PHOTOS = 10

logger = logging.getLogger("app.modules.catalog")


def _error(code: str, detail: str, status: int) -> AppError:
    return AppError(MODULE, code, detail, status=status)


def _log(msg: str, **fields: object) -> None:
    logger.info(msg, extra={"extra_fields": {k: str(v) for k, v in fields.items()}})


def _product_not_found() -> AppError:
    return _error("PRODUCT_NOT_FOUND", "Product not found", 404)


# ---------------------------------------------------------------- translations hook
#
# The i18n module translates product texts. It depends on catalog (not the other way
# round), so it plugs a lookup in here at startup, like identity does for core.auth.
TranslationLookup = Callable[
    [AsyncSession, Sequence[uuid.UUID], str], Awaitable[dict[uuid.UUID, tuple[str, str]]]
]
_translations: TranslationLookup | None = None


def set_translation_lookup(lookup: TranslationLookup) -> None:
    global _translations
    _translations = lookup


async def _texts(
    db: AsyncSession, products: Sequence[Product], locale: str
) -> dict[uuid.UUID, tuple[str, str]]:
    """(title, description) per product in ``locale``; the original where none exists."""
    out = {p.id: (p.title, p.description) for p in products}
    wanted = [p.id for p in products if p.source_locale != locale]
    if _translations is not None and wanted:
        out.update(await _translations(db, wanted, locale))
    return out


# ---------------------------------------------------------------- search hook
#
# The search module keeps a full-text index of products. Like i18n it depends on catalog,
# so it installs a matcher: query text -> subquery (product_id, rank). Without it the
# catalog falls back to a simple ILIKE on the title and brand.
SearchMatcher = Callable[[str], Any]
_matcher: SearchMatcher | None = None


def set_search_matcher(matcher: SearchMatcher | None) -> None:
    global _matcher
    _matcher = matcher


@dataclass(frozen=True)
class SearchFields:
    """Everything the search index needs about one product (original text only)."""

    product_id: uuid.UUID
    title: str
    description: str
    brand: str | None
    categories: list[str]  # names of the category and its parents, in all languages


async def search_fields(db: AsyncSession, product_id: uuid.UUID) -> SearchFields | None:
    p = await repo.find_product(db, Product.id == product_id)
    if p is None:
        return None
    brand = await repo.get_brand(db, p.brand_id) if p.brand_id else None
    names: list[str] = []
    category_id: uuid.UUID | None = p.category_id
    while category_id is not None and len(names) < 30:
        category = await repo.get_category(db, category_id)
        if category is None:
            break
        names.extend(v for v in category.names.values() if v)
        category_id = category.parent_id
    return SearchFields(p.id, p.title, p.description, brand.name if brand else None, names)


async def all_product_ids(db: AsyncSession) -> Sequence[uuid.UUID]:
    return await repo.all_product_ids(db)


async def product_cards(
    db: AsyncSession, product_ids: Sequence[uuid.UUID], locale: str
) -> list[ProductCard]:
    """Buyer-visible cards for ``product_ids`` in that order (hidden ones are left out)."""
    if not product_ids:
        return []
    f = ProductFilter(product_ids=list(product_ids))
    rows = await repo.list_products(db, _visible(), f, "newest", 0, len(product_ids))
    refs = await _refs(db, [p for p, _, _ in rows], locale)
    texts = await _texts(db, [p for p, _, _ in rows], locale)
    cards = {p.id: ProductCard(**_card_fields(p, refs, c, d, texts[p.id][0])) for p, c, d in rows}
    return [cards[i] for i in product_ids if i in cards]


@dataclass(frozen=True)
class ProductSource:
    product_id: uuid.UUID
    store_id: uuid.UUID
    source_locale: str
    title: str
    description: str


async def product_source(
    db: AsyncSession, product_id: uuid.UUID, store_id: uuid.UUID | None = None
) -> ProductSource | None:
    """The original text of a product (optionally only if it belongs to ``store_id``)."""
    conds = [Product.id == product_id]
    if store_id is not None:
        conds.append(Product.store_id == store_id)
    p = await repo.find_product(db, *conds)
    if p is None:
        return None
    return ProductSource(p.id, p.store_id, p.source_locale, p.title, p.description)


def _visible() -> ColumnElement[bool]:
    """Products a buyer may see."""
    return and_(
        Product.status == "active",
        Product.deleted_at.is_(None),
        Product.store_id.in_(stores.active_store_ids()),
    )


# ---------------------------------------------------------------- categories


@dataclass
class _Tree:
    by_id: dict[uuid.UUID, Category]
    children: dict[uuid.UUID | None, list[Category]]

    def descendants(self, root: uuid.UUID) -> list[uuid.UUID]:
        out, stack = [], [root]
        while stack:
            current = stack.pop()
            out.append(current)
            stack.extend(c.id for c in self.children.get(current, []))
        return out


async def _tree(db: AsyncSession, only_active: bool = True) -> _Tree:
    rows = [c for c in await repo.all_categories(db) if c.is_active or not only_active]
    by_id = {c.id: c for c in rows}
    children: dict[uuid.UUID | None, list[Category]] = {}
    for c in rows:
        parent = c.parent_id if c.parent_id in by_id else None
        children.setdefault(parent, []).append(c)
    return _Tree(by_id, children)


async def _category_ids(db: AsyncSession, slug: str | None) -> list[uuid.UUID] | None:
    if not slug:
        return None
    tree = await _tree(db)
    found = next((c for c in tree.by_id.values() if c.slug == slug), None)
    if found is None:
        raise _error("CATEGORY_NOT_FOUND", "Category not found", 404)
    return tree.descendants(found.id)


async def list_categories(db: AsyncSession, locale: str) -> list[CategoryOut]:
    """Category tree; ``product_count`` includes subcategories."""
    tree = await _tree(db)
    counts = await repo.count_by_category(db, _visible())

    def build(c: Category) -> CategoryOut:
        kids = [build(k) for k in tree.children.get(c.id, [])]
        own = counts.get(c.id, 0)
        return CategoryOut(
            id=c.id,
            slug=c.slug,
            name=pick(c.names, locale),
            image_url=c.image_url,
            product_count=own + sum(k.product_count for k in kids),
            children=kids,
        )

    return [build(c) for c in tree.children.get(None, [])]


async def admin_categories(db: AsyncSession) -> list[CategoryAdminOut]:
    return [CategoryAdminOut.model_validate(c) for c in await repo.all_categories(db)]


async def _check_parent(
    db: AsyncSession, parent_id: uuid.UUID | None, self_id: uuid.UUID | None = None
) -> None:
    if parent_id is None:
        return
    if await repo.get_category(db, parent_id) is None:
        raise _error("CATEGORY_NOT_FOUND", "Parent category not found", 404)
    if self_id is not None:
        tree = await _tree(db, only_active=False)
        if parent_id in tree.descendants(self_id):
            raise _error("CATEGORY_CYCLE", "A category cannot be inside itself", 409)


async def create_category(db: AsyncSession, data: CategoryIn) -> CategoryAdminOut:
    await _check_parent(db, data.parent_id)
    category = Category(id=uuid7(), **{**data.model_dump(), "names": data.names.model_dump()})
    db.add(category)
    await _commit_unique(db, "SLUG_TAKEN", "This slug is already used")
    return CategoryAdminOut.model_validate(category)


async def update_category(
    db: AsyncSession, category_id: uuid.UUID, data: CategoryUpdate
) -> CategoryAdminOut:
    category = await repo.get_category(db, category_id)
    if category is None:
        raise _error("CATEGORY_NOT_FOUND", "Category not found", 404)
    changes = data.model_dump(exclude_unset=True)
    if "parent_id" in changes:
        await _check_parent(db, changes["parent_id"], category.id)
    for name, value in changes.items():
        if name in ("names", "position", "is_active") and value is None:
            continue
        setattr(category, name, value)
    await db.commit()
    return CategoryAdminOut.model_validate(category)


# ---------------------------------------------------------------- brands


async def list_brands(db: AsyncSession, category_slug: str | None = None) -> list[BrandOut]:
    """Active brands. With ``category`` only those that have goods in it."""
    f = ProductFilter(category_ids=await _category_ids(db, category_slug))
    counts = await repo.count_by_brand(db, _visible(), f)
    out = [
        BrandOut(
            id=b.id,
            slug=b.slug,
            name=b.name,
            logo_url=b.logo_url,
            product_count=counts.get(b.id, 0),
        )
        for b in await repo.all_brands(db, only_active=True)
    ]
    if category_slug:
        out = [b for b in out if b.product_count > 0]
    return out


async def admin_brands(db: AsyncSession) -> list[BrandAdminOut]:
    return [BrandAdminOut.model_validate(b) for b in await repo.all_brands(db, only_active=False)]


async def create_brand(db: AsyncSession, data: BrandIn) -> BrandAdminOut:
    brand = Brand(id=uuid7(), **data.model_dump())
    db.add(brand)
    await _commit_unique(db, "SLUG_TAKEN", "This slug is already used")
    return BrandAdminOut.model_validate(brand)


async def update_brand(db: AsyncSession, brand_id: uuid.UUID, data: BrandUpdate) -> BrandAdminOut:
    brand = await repo.get_brand(db, brand_id)
    if brand is None:
        raise _error("BRAND_NOT_FOUND", "Brand not found", 404)
    for name, value in data.model_dump(exclude_unset=True).items():
        if name in ("name", "description", "is_active") and value is None:
            continue
        setattr(brand, name, value)
    await db.commit()
    return BrandAdminOut.model_validate(brand)


async def _commit_unique(db: AsyncSession, code: str, detail: str) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _error(code, detail, 409) from exc


# ---------------------------------------------------------------- building responses


async def _refs(
    db: AsyncSession, products: Sequence[Product], locale: str
) -> tuple[dict[uuid.UUID, RefOut], dict[uuid.UUID, RefOut], dict[uuid.UUID, RefOut]]:
    tree = await _tree(db, only_active=False)
    categories = {
        cid: RefOut(id=c.id, slug=c.slug, name=pick(c.names, locale))
        for cid, c in tree.by_id.items()
    }
    brands = {
        bid: RefOut(id=b.id, slug=b.slug, name=b.name)
        for bid, b in (
            await repo.brands_by_ids(db, {p.brand_id for p in products if p.brand_id})
        ).items()
    }
    store_refs: dict[uuid.UUID, RefOut] = {}
    for store_id in {p.store_id for p in products}:
        brief = await stores.get_store_brief(db, store_id)
        if brief is not None:
            store_refs[store_id] = RefOut(id=brief.id, slug=brief.slug, name=brief.name)
    return categories, brands, store_refs


def _card_fields(
    p: Product,
    refs: tuple[dict[uuid.UUID, RefOut], dict[uuid.UUID, RefOut], dict[uuid.UUID, RefOut]],
    cover: str | None,
    compare_at: Decimal | None,
    title: str | None = None,
) -> dict[str, object]:
    categories, brands, store_refs = refs
    return {
        "id": p.id,
        "slug": p.slug,
        "title": title or p.title,
        "min_price": p.min_price,
        "compare_at_price": compare_at,
        "currency": p.currency,
        "in_stock": p.in_stock,
        "rating_avg": p.rating_avg,
        "rating_count": p.rating_count,
        "cover_url": cover,
        "brand": brands.get(p.brand_id) if p.brand_id else None,
        "category": categories[p.category_id],
        "store": store_refs[p.store_id],
    }


def _coverage(images: Sequence[ProductImage]) -> PhotoCoverage:
    present = {i.angle for i in images if i.source == "seller" and i.status == "approved"}
    missing = [a for a in PHOTO_ANGLES if a not in present]
    return PhotoCoverage(
        present=[a for a in PHOTO_ANGLES if a in present], missing=missing, complete=not missing
    )


async def _detail_fields(
    db: AsyncSession, p: Product, locale: str, *, public: bool
) -> dict[str, object]:
    variants = await repo.variants_of(db, p.id)
    images = await repo.images_of(db, p.id)
    seller = [i for i in images if i.source == "seller"]
    buyer = [i for i in images if i.source == "buyer" and (i.status == "approved" or not public)]
    shown_variants = [v for v in variants if v.is_active or not public]
    cheapest = min((v for v in variants if v.is_active), key=lambda v: v.price, default=None)
    refs = await _refs(db, [p], locale)
    cover = next((i.url for i in seller if i.status == "approved"), None)
    # Buyers read their language; the seller sees (and edits) the original.
    title, description = (
        (await _texts(db, [p], locale))[p.id] if public else (p.title, p.description)
    )
    return {
        **_card_fields(p, refs, cover, cheapest.compare_at_price if cheapest else None, title),
        "description": description,
        "source_locale": p.source_locale,
        "specifications": p.specifications,
        "variants": [VariantOut.model_validate(v) for v in shown_variants],
        "seller_photos": [ImageOut.model_validate(i) for i in seller],
        "buyer_photos": [ImageOut.model_validate(i) for i in buyer],
        "photo_coverage": _coverage(images),
        "published_at": p.published_at,
    }


async def _seller_out(db: AsyncSession, p: Product, locale: str) -> SellerProductOut:
    return SellerProductOut(
        **(await _detail_fields(db, p, locale, public=False)),
        status=p.status,
        moderation_note=p.moderation_note,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


# ---------------------------------------------------------------- public catalog


async def list_products(
    db: AsyncSession,
    *,
    locale: str,
    category: str | None,
    brands: Sequence[str],
    store: str | None,
    q: str | None,
    price_min: Decimal | None,
    price_max: Decimal | None,
    in_stock: bool | None,
    rating_min: Decimal | None,
    sizes: Sequence[str],
    sort: Sort,
    offset: int,
    limit: int,
) -> Page[ProductCard]:
    store_id = None
    if store:
        store_id = await stores.find_store_id(db, store)
        if store_id is None:
            return Page(items=[])
    f = ProductFilter(
        category_ids=await _category_ids(db, category),
        brand_slugs=list(brands),
        store_id=store_id,
        q=q.strip() if q and q.strip() else None,
        match=_matcher(q.strip()) if _matcher and q and q.strip() else None,
        price_min=price_min,
        price_max=price_max,
        in_stock=in_stock,
        rating_min=rating_min,
        sizes=list(sizes),
    )
    rows = await repo.list_products(db, _visible(), f, sort, offset, limit + 1)
    page = rows[:limit]
    refs = await _refs(db, [p for p, _, _ in page], locale)
    texts = await _texts(db, [p for p, _, _ in page], locale)
    items = [ProductCard(**_card_fields(p, refs, c, d, texts[p.id][0])) for p, c, d in page]
    return Page(items=items, next_cursor=next_cursor(offset, limit, len(rows)))


async def filters(db: AsyncSession, locale: str, category: str | None) -> FiltersOut:
    f = ProductFilter(category_ids=await _category_ids(db, category))
    low, high = await repo.price_range(db, _visible(), f)
    tree = await _categories_for_filter(db, locale, category)
    return FiltersOut(
        categories=tree,
        brands=await list_brands(db, category),
        price=PriceRange(min=low, max=high),
        sizes=_sort_sizes(await repo.sizes(db, _visible(), f)),
    )


async def _categories_for_filter(
    db: AsyncSession, locale: str, category: str | None
) -> list[CategoryOut]:
    roots = await list_categories(db, locale)
    if not category:
        return roots
    stack = list(roots)
    while stack:
        node = stack.pop()
        if node.slug == category:
            return node.children
        stack.extend(node.children)
    return []


def _sort_sizes(values: list[str]) -> list[str]:
    def key(s: str) -> tuple[int, float, str]:
        try:
            return (0, float(s.replace(",", ".")), s)
        except ValueError:
            order = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"]
            return (1, float(order.index(s.upper())) if s.upper() in order else 99.0, s)

    return sorted(set(values), key=key)


async def get_product(db: AsyncSession, slug: str, locale: str) -> ProductDetail:
    product = await repo.find_product(db, Product.slug == slug, _visible())
    if product is None:
        raise _product_not_found()
    return ProductDetail(**(await _detail_fields(db, product, locale, public=True)))


async def add_buyer_photo(
    db: AsyncSession, principal: Principal, product_id: uuid.UUID, data: ImageIn
) -> ImageOut:
    """A buyer's own photo of the item. Shown after moderation.
    (Once orders exist: only for buyers who bought it.)"""
    product = await repo.find_product(db, Product.id == product_id, _visible())
    if product is None:
        raise _product_not_found()
    if await repo.count_buyer_photos(db, product.id, principal.user_id) >= MAX_BUYER_PHOTOS:
        raise _error("TOO_MANY_PHOTOS", f"At most {MAX_BUYER_PHOTOS} photos per product", 409)
    image = ProductImage(
        id=uuid7(),
        product_id=product.id,
        source="buyer",
        angle=data.angle,
        url=data.url,
        position=data.position,
        author_id=principal.user_id,
        status="pending",
    )
    db.add(image)
    await db.commit()
    return ImageOut.model_validate(image)


# ---------------------------------------------------------------- seller: products


async def _own_product(db: AsyncSession, access: StoreAccess, product_id: uuid.UUID) -> Product:
    product = await repo.find_product(
        db, Product.id == product_id, Product.store_id == access.store_id
    )
    if product is None:
        raise _product_not_found()
    return product


async def _check_refs(
    db: AsyncSession, category_id: uuid.UUID | None, brand_id: uuid.UUID | None
) -> None:
    if category_id is not None:
        category = await repo.get_category(db, category_id)
        if category is None or not category.is_active:
            raise _error("CATEGORY_NOT_FOUND", "Category not found", 404)
    if brand_id is not None:
        brand = await repo.get_brand(db, brand_id)
        if brand is None or not brand.is_active:
            raise _error("BRAND_NOT_FOUND", "Brand not found", 404)


async def _check_skus(db: AsyncSession, skus: Sequence[str]) -> None:
    if len(set(skus)) != len(skus):
        raise _error("SKU_TAKEN", "SKUs must be unique", 409)
    taken = await repo.sku_taken(db, skus)
    if taken:
        raise _error("SKU_TAKEN", f"SKU already used: {', '.join(sorted(taken))}", 409)


async def _free_slug(db: AsyncSession, title: str) -> str:
    slug = unique_slug(title)
    while await repo.slug_taken(db, slug):
        slug = unique_slug(title)
    return slug


async def refresh_summary(db: AsyncSession, product: Product) -> None:
    """Recomputes ``min_price`` / ``in_stock`` of a product from its active variants."""
    await db.flush()
    active = [v for v in await repo.variants_of(db, product.id) if v.is_active]
    product.min_price = min((v.price for v in active), default=None)
    product.in_stock = any(v.in_stock for v in active)


def _new_variant(product_id: uuid.UUID, v: VariantIn) -> ProductVariant:
    return ProductVariant(id=uuid7(), product_id=product_id, in_stock=False, **v.model_dump())


async def create_product(
    db: AsyncSession, access: StoreAccess, data: ProductIn, locale: str
) -> SellerProductOut:
    """Creates a draft. Publish it once it has a price and photos."""
    await _check_refs(db, data.category_id, data.brand_id)
    await _check_skus(db, [v.sku for v in data.variants])
    product = Product(
        id=uuid7(),
        store_id=access.store_id,
        category_id=data.category_id,
        brand_id=data.brand_id,
        slug=await _free_slug(db, data.title),
        source_locale=data.source_locale,
        title=data.title,
        description=data.description,
        specifications=data.specifications,
        status="draft",
    )
    db.add(product)
    await db.flush()
    for v in data.variants:
        db.add(_new_variant(product.id, v))
    await refresh_summary(db, product)
    await publish_event(db, ProductCreated(product.id, product.store_id, product.source_locale))
    await _commit_unique(db, "SKU_TAKEN", "SKU already used")
    _log("product created", product_id=product.id, store_id=access.store_id)
    return await _seller_out(db, product, locale)


async def seller_products(
    db: AsyncSession,
    access: StoreAccess,
    status: str | None,
    offset: int,
    limit: int,
    locale: str,
) -> Page[SellerProductOut]:
    rows = await repo.store_products(db, access.store_id, status, offset, limit + 1)
    items = [await _seller_out(db, p, locale) for p in rows[:limit]]
    return Page(items=items, next_cursor=next_cursor(offset, limit, len(rows)))


async def seller_product(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID, locale: str
) -> SellerProductOut:
    return await _seller_out(db, await _own_product(db, access, product_id), locale)


async def update_product(
    db: AsyncSession,
    access: StoreAccess,
    product_id: uuid.UUID,
    data: ProductUpdate,
    locale: str,
) -> SellerProductOut:
    product = await _own_product(db, access, product_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("category_id") is None:
        changes.pop("category_id", None)
    await _check_refs(db, changes.get("category_id"), changes.get("brand_id"))
    text_before = (product.title, product.description, product.source_locale)
    for name, value in changes.items():
        if value is None and name != "brand_id":
            continue
        setattr(product, name, value)
    if (product.title, product.description, product.source_locale) != text_before:
        await publish_event(db, ProductUpdated(product.id, product.store_id, product.source_locale))
    await db.commit()
    return await _seller_out(db, product, locale)


async def publish(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID, locale: str
) -> SellerProductOut:
    product = await _own_product(db, access, product_id)
    if product.status == "blocked":
        raise _error("PRODUCT_BLOCKED", "Blocked by moderation: contact support", 409)
    if product.min_price is None:
        raise _error("NO_VARIANTS", "Add at least one active variant with a price", 409)
    if not any(i.source == "seller" for i in await repo.images_of(db, product.id)):
        raise _error("NO_PHOTOS", "Add at least one photo", 409)
    product.status = "active"
    product.published_at = product.published_at or datetime.now(UTC)
    await db.commit()
    _log("product published", product_id=product.id)
    return await _seller_out(db, product, locale)


async def archive(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID, locale: str
) -> SellerProductOut:
    product = await _own_product(db, access, product_id)
    if product.status == "blocked":
        raise _error("PRODUCT_BLOCKED", "Blocked by moderation: contact support", 409)
    product.status = "archived"
    await publish_event(db, ProductArchived(product.id, product.store_id))
    await db.commit()
    return await _seller_out(db, product, locale)


async def delete_product(db: AsyncSession, access: StoreAccess, product_id: uuid.UUID) -> None:
    """Soft delete: past orders keep pointing at the product."""
    product = await _own_product(db, access, product_id)
    product.deleted_at = datetime.now(UTC)
    product.status = "archived"
    await db.commit()
    _log("product deleted", product_id=product.id)


# ---------------------------------------------------------------- seller: variants and photos


async def add_variant(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID, data: VariantIn
) -> VariantOut:
    product = await _own_product(db, access, product_id)
    await _check_skus(db, [data.sku])
    variant = _new_variant(product.id, data)
    db.add(variant)
    await refresh_summary(db, product)
    await _commit_unique(db, "SKU_TAKEN", "SKU already used")
    return VariantOut.model_validate(variant)


async def update_variant(
    db: AsyncSession,
    access: StoreAccess,
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    data: VariantUpdate,
) -> VariantOut:
    product = await _own_product(db, access, product_id)
    variant = await repo.get_variant(db, product.id, variant_id)
    if variant is None:
        raise _error("VARIANT_NOT_FOUND", "Variant not found", 404)
    for name, value in data.model_dump(exclude_unset=True).items():
        if value is None and name != "compare_at_price":
            continue
        setattr(variant, name, value)
    if variant.compare_at_price is not None and variant.compare_at_price <= variant.price:
        raise _error("BAD_PRICE", "compare_at_price must be higher than price", 422)
    await refresh_summary(db, product)
    await db.commit()
    return VariantOut.model_validate(variant)


async def delete_variant(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID, variant_id: uuid.UUID
) -> None:
    product = await _own_product(db, access, product_id)
    variant = await repo.get_variant(db, product.id, variant_id)
    if variant is None:
        raise _error("VARIANT_NOT_FOUND", "Variant not found", 404)
    await db.delete(variant)
    await refresh_summary(db, product)
    await db.commit()


async def add_image(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID, data: ImageIn
) -> ImageOut:
    """A seller photo for one side (angle). A new photo of the same side replaces the old one."""
    product = await _own_product(db, access, product_id)
    images = await repo.images_of(db, product.id)
    seller = [i for i in images if i.source == "seller"]
    if data.angle != "other":
        for old in [i for i in seller if i.angle == data.angle]:
            await db.delete(old)
            seller.remove(old)
    if len(seller) >= MAX_IMAGES:
        raise _error("TOO_MANY_PHOTOS", f"At most {MAX_IMAGES} photos per product", 409)
    image = ProductImage(
        id=uuid7(),
        product_id=product.id,
        source="seller",
        angle=data.angle,
        url=data.url,
        position=data.position,
        author_id=access.user_id,
        status="approved",
    )
    db.add(image)
    await db.commit()
    return ImageOut.model_validate(image)


async def delete_image(
    db: AsyncSession, access: StoreAccess, product_id: uuid.UUID, image_id: uuid.UUID
) -> None:
    product = await _own_product(db, access, product_id)
    image = await repo.get_image(db, image_id)
    if image is None or image.product_id != product.id or image.source != "seller":
        raise _error("IMAGE_NOT_FOUND", "Photo not found", 404)
    await db.delete(image)
    await db.commit()


# ---------------------------------------------------------------- admin moderation


async def moderate_product(
    db: AsyncSession, actor: Principal, product_id: uuid.UUID, data: ModerateIn, locale: str
) -> SellerProductOut:
    product = await repo.find_product(db, Product.id == product_id)
    if product is None:
        raise _product_not_found()
    if data.action == "block":
        product.status = "blocked"
    elif product.status == "blocked":
        product.status = "draft"  # the seller checks it and publishes again
    product.moderation_note = data.note
    await db.commit()
    _log("product moderated", product_id=product.id, action=data.action, actor=actor.user_id)
    return await _seller_out(db, product, locale)


async def moderate_image(
    db: AsyncSession, actor: Principal, image_id: uuid.UUID, status: str
) -> ImageOut:
    image = await repo.get_image(db, image_id)
    if image is None:
        raise _error("IMAGE_NOT_FOUND", "Photo not found", 404)
    image.status = status
    await db.commit()
    _log("photo moderated", image_id=image.id, status=status, actor=actor.user_id)
    return ImageOut.model_validate(image)


# ---------------------------------------------------------------- for the inventory module


@dataclass(frozen=True)
class VariantBrief:
    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_title: str
    product_status: str
    sku: str
    attributes: dict[str, str]
    is_active: bool


async def store_variants(
    db: AsyncSession, store_id: uuid.UUID, variant_id: uuid.UUID | None = None
) -> list[VariantBrief]:
    """Variants of a store's (not deleted) products; one of them with ``variant_id``."""
    return [
        VariantBrief(v.id, p.id, p.title, p.status, v.sku, v.attributes, v.is_active)
        for v, p in await repo.store_variants(db, store_id, variant_id)
    ]


async def set_variant_in_stock(db: AsyncSession, variant_id: uuid.UUID, in_stock: bool) -> None:
    """Called by inventory when stock changes. Does not commit (same transaction)."""
    variant = await db.get(ProductVariant, variant_id)
    if variant is None or variant.in_stock == in_stock:
        return
    variant.in_stock = in_stock
    product = await db.get(Product, variant.product_id)
    if product is not None:
        await refresh_summary(db, product)


# ---------------------------------------------------------------- for cart and orders


@dataclass(frozen=True)
class VariantForSale:
    """What a buyer needs to know about a variant to put it in a cart or an order."""

    variant_id: uuid.UUID
    product_id: uuid.UUID
    product_slug: str
    product_title: str
    store_id: uuid.UUID
    sku: str
    attributes: dict[str, str]
    price: Decimal
    compare_at_price: Decimal | None
    currency: str
    cover_url: str | None
    sellable: bool  # product visible to buyers and the variant active


async def variants_for_sale(
    db: AsyncSession, variant_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, VariantForSale]:
    if not variant_ids:
        return {}
    active_stores = set(await db.scalars(stores.active_store_ids()))
    out: dict[uuid.UUID, VariantForSale] = {}
    for v, p, cover in await repo.variants_with_products(db, variant_ids):
        visible = p.status == "active" and p.deleted_at is None and p.store_id in active_stores
        out[v.id] = VariantForSale(
            variant_id=v.id,
            product_id=p.id,
            product_slug=p.slug,
            product_title=p.title,
            store_id=p.store_id,
            sku=v.sku,
            attributes=v.attributes,
            price=v.price,
            compare_at_price=v.compare_at_price,
            currency=p.currency,
            cover_url=cover,
            sellable=visible and v.is_active,
        )
    return out


async def find_variant_id(db: AsyncSession, sku: str) -> uuid.UUID | None:
    return await repo.variant_id_by_sku(db, sku)
