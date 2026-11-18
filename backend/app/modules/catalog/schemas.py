"""Request and response bodies of the `catalog` API. Input models forbid unknown fields.

Money is a decimal and travels as a string (``"125000.00"``) so JavaScript keeps precision.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Locale = Literal["uz", "ru", "en"]
Angle = Literal["left", "right", "top", "sole", "inside", "back", "label", "other"]
Slug = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80),
]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20000)]
Url = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^https?://", max_length=1000)
]
Sku = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9._-]+$", max_length=64)
]
Money = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Names(_In):
    uz: Name
    ru: Name
    en: Name


# ---------------------------------------------------------------- categories and brands


class CategoryIn(_In):
    slug: Slug
    names: Names
    parent_id: uuid.UUID | None = None
    image_url: Url | None = None
    position: int = 0
    is_active: bool = True


class CategoryUpdate(_In):
    names: Names | None = None
    parent_id: uuid.UUID | None = None
    image_url: Url | None = None
    position: int | None = None
    is_active: bool | None = None


class CategoryOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    image_url: str | None
    product_count: int = 0
    children: list["CategoryOut"] = Field(default_factory=list)


class CategoryAdminOut(_Out):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    slug: str
    names: dict[str, str]
    image_url: str | None
    position: int
    is_active: bool


class BrandIn(_In):
    slug: Slug
    name: Name
    description: Text = ""
    logo_url: Url | None = None
    is_active: bool = True


class BrandUpdate(_In):
    name: Name | None = None
    description: Text | None = None
    logo_url: Url | None = None
    is_active: bool | None = None


class BrandOut(_Out):
    id: uuid.UUID
    slug: str
    name: str
    logo_url: str | None
    product_count: int = 0


class BrandAdminOut(BrandOut):
    description: str
    is_active: bool


# ---------------------------------------------------------------- products


class VariantIn(_In):
    sku: Sku
    attributes: dict[
        Annotated[str, StringConstraints(max_length=40)],
        Annotated[str, StringConstraints(max_length=80)],
    ] = Field(default_factory=dict, description='e.g. {"size": "42", "color": "white"}')
    price: Money
    compare_at_price: Money | None = None
    position: int = 0
    is_active: bool = True

    @model_validator(mode="after")
    def _old_price_higher(self) -> Self:
        if self.compare_at_price is not None and self.compare_at_price <= self.price:
            raise ValueError("compare_at_price must be higher than price")
        return self


class VariantUpdate(_In):
    attributes: dict[str, str] | None = None
    price: Money | None = None
    compare_at_price: Money | None = None
    position: int | None = None
    is_active: bool | None = None


class VariantOut(_Out):
    id: uuid.UUID
    sku: str
    attributes: dict[str, str]
    price: Decimal
    compare_at_price: Decimal | None
    position: int
    is_active: bool
    in_stock: bool


class ImageIn(_In):
    url: Url
    angle: Angle = "other"
    position: int = 0


class ImageOut(_Out):
    id: uuid.UUID
    source: str
    angle: str
    url: str
    position: int
    status: str
    ai_check: str
    created_at: datetime


class ImageModerateIn(_In):
    status: Literal["approved", "rejected"]


class ProductIn(_In):
    title: Title
    description: Text = ""
    source_locale: Locale = "ru"
    category_id: uuid.UUID
    brand_id: uuid.UUID | None = None
    specifications: dict[str, Any] = Field(default_factory=dict)
    variants: list[VariantIn] = Field(default_factory=list, max_length=100)


class ProductUpdate(_In):
    title: Title | None = None
    description: Text | None = None
    source_locale: Locale | None = None
    category_id: uuid.UUID | None = None
    brand_id: uuid.UUID | None = None
    specifications: dict[str, Any] | None = None


class ModerateIn(_In):
    action: Literal["block", "unblock"]
    note: Note | None = None


class RefOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class PhotoCoverage(BaseModel):
    """Which of the seven sides the seller has photographed."""

    present: list[str]
    missing: list[str]
    complete: bool


class ProductCard(BaseModel):
    """A product in a list (catalog, search, store page)."""

    id: uuid.UUID
    slug: str
    title: str
    min_price: Decimal | None
    compare_at_price: Decimal | None
    currency: str
    in_stock: bool
    rating_avg: Decimal
    rating_count: int
    cover_url: str | None
    brand: RefOut | None
    category: RefOut
    store: RefOut


class ProductDetail(ProductCard):
    description: str
    source_locale: str
    specifications: dict[str, Any]
    variants: list[VariantOut]
    seller_photos: list[ImageOut]
    buyer_photos: list[ImageOut]
    photo_coverage: PhotoCoverage
    published_at: datetime | None


class SellerProductOut(ProductDetail):
    status: str
    moderation_note: str | None
    created_at: datetime
    updated_at: datetime


class PriceRange(BaseModel):
    min: Decimal | None
    max: Decimal | None


class FiltersOut(BaseModel):
    """Everything the filter buttons need for the current category."""

    categories: list[CategoryOut]
    brands: list[BrandOut]
    price: PriceRange
    sizes: list[str]
