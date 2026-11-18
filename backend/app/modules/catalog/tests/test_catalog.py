import pytest

from tests.factories import (
    API,
    category_and_brand,
    open_store,
    product_body,
    published_product,
    user_with_role,
)

pytestmark = pytest.mark.usefixtures("database")


@pytest.fixture
async def setup(client):
    admin, _ = await user_with_role(client, "admin")
    shop = await open_store(client, admin)
    parent, child, brand = await category_and_brand(client, admin)
    return admin, shop, parent, child, brand


async def test_only_catalog_managers_edit_categories_and_brands(client):
    customer, _ = await user_with_role(client)
    r = await client.post(
        f"{API}/admin/brands", json={"slug": "nope", "name": "Nope"}, headers=customer.auth
    )
    assert r.status_code == 403


async def test_category_names_follow_the_requested_language(client, setup):
    _, _, parent, _, _ = setup
    tree = (await client.get(f"{API}/categories", headers={"Accept-Language": "ru-RU,ru"})).json()
    node = next(c for c in tree if c["slug"] == parent["slug"])
    assert node["name"] == "Обувь"
    assert node["children"][0]["name"] == "Кроссовки"
    tree = (await client.get(f"{API}/categories?lang=en")).json()
    assert next(c for c in tree if c["slug"] == parent["slug"])["name"] == "Shoes"


async def test_category_cannot_be_moved_inside_itself(client, setup):
    admin, _, parent, child, _ = setup
    r = await client.patch(
        f"{API}/admin/categories/{parent['id']}",
        json={"parent_id": child["id"]},
        headers=admin.auth,
    )
    assert r.json()["code"] == "CATALOG.CATEGORY_CYCLE"


async def test_publishing_needs_a_photo_and_draft_is_not_public(client, setup):
    _, shop, _, child, brand = setup
    r = await client.post(
        f"{API}/seller/products", json=product_body(child["id"], brand["id"]), headers=shop.headers
    )
    assert r.status_code == 201
    product = r.json()
    assert product["status"] == "draft"
    assert product["min_price"] == "990000.00"
    assert product["photo_coverage"]["missing"] == [
        "left",
        "right",
        "top",
        "sole",
        "inside",
        "back",
        "label",
    ]
    assert (await client.get(f"{API}/products/{product['slug']}")).status_code == 404

    r = await client.post(f"{API}/seller/products/{product['id']}/publish", headers=shop.headers)
    assert r.json()["code"] == "CATALOG.NO_PHOTOS"


async def test_seven_sides_and_buyer_photos_on_the_product_page(client, setup):
    admin, shop, _, child, brand = setup
    product = await published_product(client, shop, child["id"], brand["id"])
    for side in ["right", "top", "sole", "inside", "back", "label", "left"]:
        r = await client.post(
            f"{API}/seller/products/{product['id']}/images",
            json={"url": f"https://img.example.com/{side}.jpg", "angle": side},
            headers=shop.headers,
        )
        assert r.status_code == 201
    page = (await client.get(f"{API}/products/{product['slug']}")).json()
    assert page["photo_coverage"]["complete"] is True
    assert len(page["seller_photos"]) == 7  # the second "left" replaced the first

    buyer, _ = await user_with_role(client)
    r = await client.post(
        f"{API}/products/{product['id']}/buyer-photos",
        json={"url": "https://img.example.com/mine.jpg"},
        headers=buyer.auth,
    )
    assert r.status_code == 201
    assert r.json()["status"] == "pending"
    page = (await client.get(f"{API}/products/{product['slug']}")).json()
    assert page["buyer_photos"] == []  # waits for moderation

    r = await client.post(
        f"{API}/admin/product-images/{r.json()['id']}/moderate",
        json={"status": "approved"},
        headers=admin.auth,
    )
    assert r.status_code == 200
    page = (await client.get(f"{API}/products/{product['slug']}")).json()
    assert [p["url"] for p in page["buyer_photos"]] == ["https://img.example.com/mine.jpg"]


async def test_filters_by_category_tree_brand_price_and_store(client, setup):
    _, shop, parent, child, brand = setup
    cheap = await published_product(client, shop, child["id"], brand["id"], price="500000")
    pricey = await published_product(client, shop, parent["id"], None, price="1500000")

    async def titles(query: str) -> list[str]:
        r = await client.get(f"{API}/products?{query}")
        assert r.status_code == 200, r.text
        return [i["title"] for i in r.json()["items"]]

    # The parent category includes its subcategory.
    assert set(await titles(f"category={parent['slug']}")) == {cheap["title"], pricey["title"]}
    assert await titles(f"category={child['slug']}") == [cheap["title"]]
    assert await titles(f"brand={brand['slug']}") == [cheap["title"]]
    assert await titles(f"store={shop.slug}&sort=price_desc") == [pricey["title"], cheap["title"]]
    assert await titles(f"store={shop.slug}&price_min=1000000") == [pricey["title"]]
    assert await titles(f"store={shop.slug}&q={cheap['title'][-8:]}") == [cheap["title"]]

    first = (await client.get(f"{API}/products?store={shop.slug}&limit=1")).json()
    assert len(first["items"]) == 1
    second = (
        await client.get(f"{API}/products?store={shop.slug}&limit=1&cursor={first['next_cursor']}")
    ).json()
    assert second["items"][0]["id"] != first["items"][0]["id"]
    assert second["next_cursor"] is None

    filters = (await client.get(f"{API}/catalog/filters?category={parent['slug']}")).json()
    assert [c["slug"] for c in filters["categories"]] == [child["slug"]]
    assert [b["slug"] for b in filters["brands"]] == [brand["slug"]]
    assert filters["price"] == {"min": "500000.00", "max": "1500000.00"}
    assert filters["sizes"] == ["41", "42"]


async def test_sellers_cannot_touch_other_stores_products(client, setup):
    admin, shop, _, child, brand = setup
    product = await published_product(client, shop, child["id"], brand["id"])
    other = await open_store(client, admin)
    r = await client.patch(
        f"{API}/seller/products/{product['id']}", json={"title": "Hacked"}, headers=other.headers
    )
    assert r.status_code == 404
    r = await client.delete(f"{API}/seller/products/{product['id']}", headers=other.headers)
    assert r.status_code == 404


async def test_admin_block_hides_product_and_seller_cannot_republish(client, setup):
    admin, shop, _, child, brand = setup
    product = await published_product(client, shop, child["id"], brand["id"])
    r = await client.post(
        f"{API}/admin/products/{product['id']}/moderate",
        json={"action": "block", "note": "подделка"},
        headers=admin.auth,
    )
    assert r.json()["status"] == "blocked"
    assert (await client.get(f"{API}/products/{product['slug']}")).status_code == 404
    r = await client.post(f"{API}/seller/products/{product['id']}/publish", headers=shop.headers)
    assert r.json()["code"] == "CATALOG.PRODUCT_BLOCKED"


async def test_variants_drive_min_price_and_sku_is_unique(client, setup):
    _, shop, _, child, brand = setup
    product = await published_product(client, shop, child["id"], brand["id"], price="800000")
    variant = product["variants"][0]
    r = await client.post(
        f"{API}/seller/products/{product['id']}/variants",
        json={"sku": variant["sku"], "price": "1"},
        headers=shop.headers,
    )
    assert r.json()["code"] == "CATALOG.SKU_TAKEN"

    r = await client.patch(
        f"{API}/seller/products/{product['id']}/variants/{variant['id']}",
        json={"price": "700000", "compare_at_price": "900000"},
        headers=shop.headers,
    )
    assert r.status_code == 200
    page = (await client.get(f"{API}/products/{product['slug']}")).json()
    assert page["min_price"] == "700000.00"
    assert page["compare_at_price"] == "900000.00"

    r = await client.patch(
        f"{API}/seller/products/{product['id']}/variants/{variant['id']}",
        json={"compare_at_price": "100"},
        headers=shop.headers,
    )
    assert r.json()["code"] == "CATALOG.BAD_PRICE"
