"""Shared test helpers for module tests that need users with roles, stores and products.

Lives outside ``app/modules`` so any module's tests may use it without crossing module
boundaries (tests/test_module_boundaries.py checks only app/modules).
"""

import uuid
from dataclasses import dataclass
from typing import Any

from httpx import AsyncClient

from app.core.db import get_sessionmaker
from app.modules.identity import service as identity
from app.modules.identity.tests.helpers import API, Login, register

__all__ = ["API", "Login"]


Json = dict[str, Any]


def uid() -> str:
    return uuid.uuid4().hex[:8]


async def user_with_role(client: AsyncClient, role: str | None = None) -> tuple[Login, str]:
    """A registered user (and their email), optionally with a platform role."""
    me, payload = await register(client)
    email = str(payload["email"])
    if role:
        async with get_sessionmaker()() as db:
            user_id = await identity.find_user_id(db, email)
            assert user_id is not None
            await identity.grant_role(db, user_id, role)
    return me, email


@dataclass
class Shop:
    owner: Login
    owner_email: str
    store_id: str
    slug: str

    @property
    def headers(self) -> dict[str, str]:
        return {**self.owner.auth, "X-Store-Id": self.store_id}


async def open_store(client: AsyncClient, admin: Login, name: str | None = None) -> Shop:
    """Applies for a store as a new user and approves it as ``admin``."""
    owner, email = await user_with_role(client)
    r = await client.post(
        f"{API}/seller/applications",
        json={"store_name": name or f"Shop {uid()}", "phone": "+998901112233"},
        headers=owner.auth,
    )
    assert r.status_code == 201, r.text
    r = await client.post(
        f"{API}/admin/seller-applications/{r.json()['id']}/approve", headers=admin.auth
    )
    assert r.status_code == 200, r.text
    store_id = r.json()["store_id"]
    store = (await client.get(f"{API}/seller/store", headers=owner.auth)).json()
    return Shop(owner, email, store_id, store["slug"])


async def category_and_brand(client: AsyncClient, admin: Login) -> tuple[Json, Json, Json]:
    """A parent category, its child and a brand, all with unique slugs."""
    tag = uid()
    parent = await client.post(
        f"{API}/admin/categories",
        json={"slug": f"shoes-{tag}", "names": {"uz": "Poyabzal", "ru": "Обувь", "en": "Shoes"}},
        headers=admin.auth,
    )
    assert parent.status_code == 201, parent.text
    child = await client.post(
        f"{API}/admin/categories",
        json={
            "slug": f"sneakers-{tag}",
            "names": {"uz": "Krossovkalar", "ru": "Кроссовки", "en": "Sneakers"},
            "parent_id": parent.json()["id"],
        },
        headers=admin.auth,
    )
    assert child.status_code == 201, child.text
    brand = await client.post(
        f"{API}/admin/brands",
        json={"slug": f"brand-{tag}", "name": f"Brand {tag}"},
        headers=admin.auth,
    )
    assert brand.status_code == 201, brand.text
    return parent.json(), child.json(), brand.json()


def product_body(
    category_id: str,
    brand_id: str | None,
    *,
    sizes: tuple[str, ...] = ("41", "42"),
    price: str = "990000",
) -> Json:
    tag = uid()
    return {
        "title": f"Test sneaker {tag}",
        "description": "Описание",
        "source_locale": "ru",
        "category_id": category_id,
        "brand_id": brand_id,
        "variants": [
            {"sku": f"T-{tag}-{s}", "attributes": {"size": s}, "price": price} for s in sizes
        ],
    }


async def published_product(
    client: AsyncClient, shop: Shop, category_id: str, brand_id: str | None, **kw: Any
) -> Json:
    r = await client.post(
        f"{API}/seller/products",
        json=product_body(category_id, brand_id, **kw),
        headers=shop.headers,
    )
    assert r.status_code == 201, r.text
    product = r.json()
    r = await client.post(
        f"{API}/seller/products/{product['id']}/images",
        json={"url": "https://img.example.com/left.jpg", "angle": "left"},
        headers=shop.headers,
    )
    assert r.status_code == 201, r.text
    r = await client.post(f"{API}/seller/products/{product['id']}/publish", headers=shop.headers)
    assert r.status_code == 200, r.text
    published: Json = r.json()
    return published
