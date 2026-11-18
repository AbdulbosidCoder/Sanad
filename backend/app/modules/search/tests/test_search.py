import pytest

from tests.factories import (
    API,
    category_and_brand,
    open_store,
    published_product,
    uid,
    user_with_role,
)

pytestmark = pytest.mark.usefixtures("database")


@pytest.fixture
async def shop(client):
    admin, _ = await user_with_role(client, "admin")
    _, child, brand = await category_and_brand(client, admin)
    shop = await open_store(client, admin)
    return shop, child, brand


async def _create(client, shop, child, brand, title, description=""):
    product = await published_product(client, shop, child["id"], brand["id"])
    r = await client.patch(
        f"{API}/seller/products/{product['id']}",
        json={"title": title, "description": description},
        headers=shop.headers,
    )
    assert r.status_code == 200, r.text
    return product


async def test_full_text_prefix_typo_and_brand(client, shop):
    s, child, brand = shop
    w = "zorbex" + "".join(ch for ch in uid() if ch.isalpha())[:4]  # unique per run
    a = await _create(client, s, child, brand, f"{w} Runner 3000", "Лёгкие беговые кроссовки")
    b = await _create(client, s, child, brand, f"{w} Trail", "Для гор")

    async def ids(q, **params):
        r = await client.get(f"{API}/search", params={"q": q, **params})
        assert r.status_code == 200, r.text
        return [p["id"] for p in r.json()["items"]]

    assert set(await ids(w)) >= {a["id"], b["id"]}
    assert a["id"] in await ids(f"{w[:-2]} run")  # word prefixes
    assert a["id"] in await ids(f"{w} беговые")  # description, Cyrillic
    assert a["id"] in await ids(f"{w}x runner")  # typo
    assert b["id"] not in await ids(f"{w} runner 3000")
    assert a["id"] in await ids(f"{brand['name']} runner")  # brand name
    assert a["id"] in await ids(f"Krossovkalar {w}")  # category name in Uzbek
    # catalog listing uses the same index
    r = await client.get(f"{API}/products", params={"q": f"{w} trail"})
    assert r.json()["items"][0]["id"] == b["id"]


async def test_history_suggest_and_popular(client, shop):
    s, child, brand = shop
    await _create(client, s, child, brand, "Quellmo Classic")
    buyer, _ = await user_with_role(client)
    r = await client.get(f"{API}/search", params={"q": "  Quellmo!  "}, headers=buyer.auth)
    assert r.status_code == 200
    history = (await client.get(f"{API}/me/search-history", headers=buyer.auth)).json()
    assert history[0]["query"] == "quellmo"

    r = await client.get(
        f"{API}/search/suggest", params={"q": "quel", "lang": "ru"}, headers=buyer.auth
    )
    kinds = {(i["kind"], i["text"]) for i in r.json()["items"]}
    assert ("history", "quellmo") in kinds
    assert ("product", "Quellmo Classic") in kinds

    popular = (await client.get(f"{API}/search/popular")).json()
    assert any(p["query"] == "quellmo" for p in popular)

    r = await client.delete(f"{API}/me/search-history", headers=buyer.auth)
    assert r.status_code == 204
    assert (await client.get(f"{API}/me/search-history", headers=buyer.auth)).json() == []


async def test_archived_products_are_not_found(client, shop):
    s, child, brand = shop
    p = await _create(client, s, child, brand, "Vexalor Boot")
    r = await client.post(f"{API}/seller/products/{p['id']}/archive", headers=s.headers)
    assert r.status_code == 200, r.text
    r = await client.get(f"{API}/search", params={"q": "vexalor"})
    assert r.json()["items"] == []


async def test_reindex_needs_permission(client):
    buyer, _ = await user_with_role(client)
    assert (await client.post(f"{API}/admin/search/reindex", headers=buyer.auth)).status_code == 403
    dev, _ = await user_with_role(client, "developer")
    r = await client.post(f"{API}/admin/search/reindex", headers=dev.auth)
    assert r.status_code == 200 and r.json()["products"] >= 0
