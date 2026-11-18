"""Response bodies of the `recommendations` API (home page and product page blocks)."""

from pydantic import BaseModel

from app.modules.catalog.service import BrandOut, CategoryOut, ProductCard


class Block(BaseModel):
    key: str  # new | sale | trending | bestsellers | for_you | similar | also_viewed
    title: str
    items: list[ProductCard]


class HomeOut(BaseModel):
    categories: list[CategoryOut]
    brands: list[BrandOut]
    blocks: list[Block]
