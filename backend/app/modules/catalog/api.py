"""HTTP endpoints of the `catalog` module. Business logic lives in service.py."""

import uuid
from decimal import Decimal
from typing import Literal

from fastapi import Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_permission, require_sensitive_action
from app.core.db import get_session
from app.core.locale import Locale, request_locale
from app.core.modules import module_router
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, Page, decode_cursor
from app.modules.catalog import service
from app.modules.catalog.repository import Sort
from app.modules.catalog.schemas import (
    BrandAdminOut,
    BrandIn,
    BrandOut,
    BrandUpdate,
    CategoryAdminOut,
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    FiltersOut,
    ImageIn,
    ImageModerateIn,
    ImageOut,
    ModerateIn,
    ProductCard,
    ProductDetail,
    ProductIn,
    ProductUpdate,
    SellerProductOut,
    VariantIn,
    VariantOut,
    VariantUpdate,
)
from app.modules.stores.service import StoreAccess, store_access

router = module_router("catalog")

ProductStatus = Literal["draft", "active", "archived", "blocked"]
Cursor = Query(None, description="next_cursor from the previous page")
Limit = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)

_read = store_access()
_write = store_access("products.write")


def _offset(cursor: str | None) -> int:
    return decode_cursor(cursor, "catalog")


# ---------------------------------------------------------------- public


@router.get("/categories")
async def categories(
    locale: Locale = Depends(request_locale), db: AsyncSession = Depends(get_session)
) -> list[CategoryOut]:
    """Category tree in the requested language, with product counts."""
    return await service.list_categories(db, locale)


@router.get("/brands")
async def brands(
    category: str | None = Query(None, description="category slug: only brands with goods there"),
    db: AsyncSession = Depends(get_session),
) -> list[BrandOut]:
    return await service.list_brands(db, category)


@router.get("/catalog/filters")
async def catalog_filters(
    category: str | None = Query(None, description="category slug"),
    locale: Locale = Depends(request_locale),
    db: AsyncSession = Depends(get_session),
) -> FiltersOut:
    """Filter buttons for a category: subcategories, brands, price range, sizes."""
    return await service.filters(db, locale, category)


@router.get("/products")
async def products(
    q: str | None = Query(None, max_length=100, description="search in title and brand"),
    category: str | None = Query(None, description="category slug, includes subcategories"),
    brand: list[str] = Query(default_factory=list, description="brand slug; repeat for several"),
    store: str | None = Query(None, description="store slug"),
    size: list[str] = Query(default_factory=list, description="variant size; repeat for several"),
    price_min: Decimal | None = Query(None, ge=0),
    price_max: Decimal | None = Query(None, ge=0),
    in_stock: bool | None = None,
    rating_min: Decimal | None = Query(None, ge=0, le=5),
    sort: Sort | None = Query(None, description="default: relevance with q, otherwise newest"),
    cursor: str | None = Cursor,
    limit: int = Limit,
    locale: Locale = Depends(request_locale),
    db: AsyncSession = Depends(get_session),
) -> Page[ProductCard]:
    return await service.list_products(
        db,
        locale=locale,
        category=category,
        brands=brand,
        store=store,
        q=q,
        price_min=price_min,
        price_max=price_max,
        in_stock=in_stock,
        rating_min=rating_min,
        sizes=size,
        sort=sort or ("relevance" if q else "newest"),
        offset=_offset(cursor),
        limit=limit,
    )


@router.get("/products/{slug}")
async def product(
    slug: str, locale: Locale = Depends(request_locale), db: AsyncSession = Depends(get_session)
) -> ProductDetail:
    """Product page: variants, seller photos by side, approved buyer photos."""
    return await service.get_product(db, slug, locale)


@router.post("/products/{product_id}/buyer-photos", status_code=status.HTTP_201_CREATED)
async def add_buyer_photo(
    product_id: uuid.UUID,
    data: ImageIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> ImageOut:
    """A buyer's real photo of the item. Visible after moderation."""
    return await service.add_buyer_photo(db, principal, product_id, data)


# ---------------------------------------------------------------- seller


@router.get("/seller/products")
async def seller_products(
    status_: ProductStatus | None = Query(None, alias="status"),
    cursor: str | None = Cursor,
    limit: int = Limit,
    locale: Locale = Depends(request_locale),
    access: StoreAccess = Depends(_read),
    db: AsyncSession = Depends(get_session),
) -> Page[SellerProductOut]:
    return await service.seller_products(db, access, status_, _offset(cursor), limit, locale)


@router.post("/seller/products", status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductIn,
    locale: Locale = Depends(request_locale),
    access: StoreAccess = Depends(_write),
    db: AsyncSession = Depends(get_session),
) -> SellerProductOut:
    return await service.create_product(db, access, data, locale)


@router.get("/seller/products/{product_id}")
async def seller_product(
    product_id: uuid.UUID,
    locale: Locale = Depends(request_locale),
    access: StoreAccess = Depends(_read),
    db: AsyncSession = Depends(get_session),
) -> SellerProductOut:
    return await service.seller_product(db, access, product_id, locale)


@router.patch("/seller/products/{product_id}")
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    locale: Locale = Depends(request_locale),
    access: StoreAccess = Depends(_write),
    db: AsyncSession = Depends(get_session),
) -> SellerProductOut:
    return await service.update_product(db, access, product_id, data, locale)


@router.post("/seller/products/{product_id}/publish")
async def publish(
    product_id: uuid.UUID,
    locale: Locale = Depends(request_locale),
    access: StoreAccess = Depends(_write),
    db: AsyncSession = Depends(get_session),
) -> SellerProductOut:
    """Shows the product to buyers. Needs an active variant and at least one photo."""
    return await service.publish(db, access, product_id, locale)


@router.post("/seller/products/{product_id}/archive")
async def archive(
    product_id: uuid.UUID,
    locale: Locale = Depends(request_locale),
    access: StoreAccess = Depends(_write),
    db: AsyncSession = Depends(get_session),
) -> SellerProductOut:
    return await service.archive(db, access, product_id, locale)


@router.delete("/seller/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    access: StoreAccess = Depends(store_access("products.delete")),
    db: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_product(db, access, product_id)


@router.post("/seller/products/{product_id}/variants", status_code=status.HTTP_201_CREATED)
async def add_variant(
    product_id: uuid.UUID,
    data: VariantIn,
    access: StoreAccess = Depends(_write),
    db: AsyncSession = Depends(get_session),
) -> VariantOut:
    return await service.add_variant(db, access, product_id, data)


@router.patch("/seller/products/{product_id}/variants/{variant_id}")
async def update_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    data: VariantUpdate,
    access: StoreAccess = Depends(_write),
    db: AsyncSession = Depends(get_session),
) -> VariantOut:
    return await service.update_variant(db, access, product_id, variant_id, data)


@router.delete(
    "/seller/products/{product_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_variant(
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    access: StoreAccess = Depends(_write),
    db: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_variant(db, access, product_id, variant_id)


@router.post("/seller/products/{product_id}/images", status_code=status.HTTP_201_CREATED)
async def add_image(
    product_id: uuid.UUID,
    data: ImageIn,
    access: StoreAccess = Depends(_write),
    db: AsyncSession = Depends(get_session),
) -> ImageOut:
    """Photo of one side: left, right, top, sole, inside, back, label (or other)."""
    return await service.add_image(db, access, product_id, data)


@router.delete(
    "/seller/products/{product_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    access: StoreAccess = Depends(_write),
    db: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_image(db, access, product_id, image_id)


# ---------------------------------------------------------------- admin

_manage = require_permission("catalog.manage")


@router.get("/admin/categories")
async def admin_categories(
    _: Principal = Depends(_manage), db: AsyncSession = Depends(get_session)
) -> list[CategoryAdminOut]:
    return await service.admin_categories(db)


@router.post("/admin/categories", status_code=status.HTTP_201_CREATED)
async def create_category(
    data: CategoryIn, _: Principal = Depends(_manage), db: AsyncSession = Depends(get_session)
) -> CategoryAdminOut:
    return await service.create_category(db, data)


@router.patch("/admin/categories/{category_id}")
async def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    _: Principal = Depends(_manage),
    db: AsyncSession = Depends(get_session),
) -> CategoryAdminOut:
    return await service.update_category(db, category_id, data)


@router.get("/admin/brands")
async def admin_brands(
    _: Principal = Depends(_manage), db: AsyncSession = Depends(get_session)
) -> list[BrandAdminOut]:
    return await service.admin_brands(db)


@router.post("/admin/brands", status_code=status.HTTP_201_CREATED)
async def create_brand(
    data: BrandIn, _: Principal = Depends(_manage), db: AsyncSession = Depends(get_session)
) -> BrandAdminOut:
    return await service.create_brand(db, data)


@router.patch("/admin/brands/{brand_id}")
async def update_brand(
    brand_id: uuid.UUID,
    data: BrandUpdate,
    _: Principal = Depends(_manage),
    db: AsyncSession = Depends(get_session),
) -> BrandAdminOut:
    return await service.update_brand(db, brand_id, data)


@router.post("/admin/products/{product_id}/moderate")
async def moderate_product(
    product_id: uuid.UUID,
    data: ModerateIn,
    locale: Locale = Depends(request_locale),
    principal: Principal = Depends(require_sensitive_action("products.moderate")),
    db: AsyncSession = Depends(get_session),
) -> SellerProductOut:
    """Block a product (hidden from buyers, the seller cannot publish it) or unblock it."""
    return await service.moderate_product(db, principal, product_id, data, locale)


@router.post("/admin/product-images/{image_id}/moderate")
async def moderate_image(
    image_id: uuid.UUID,
    data: ImageModerateIn,
    principal: Principal = Depends(require_permission("products.moderate")),
    db: AsyncSession = Depends(get_session),
) -> ImageOut:
    """Approve or reject a buyer photo."""
    return await service.moderate_image(db, principal, image_id, data.status)
