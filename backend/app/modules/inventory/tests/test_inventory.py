import pytest

from tests.factories import API, category_and_brand, open_store, published_product, user_with_role

pytestmark = pytest.mark.usefixtures("database")


async def test_stock_changes_are_logged_and_drive_availability(client):
    admin, _ = await user_with_role(client, "admin")
    shop = await open_store(client, admin)
    _, child, brand = await category_and_brand(client, admin)
    product = await published_product(client, shop, child["id"], brand["id"])
    v41, v42 = product["variants"]

    stock = (await client.get(f"{API}/seller/inventory", headers=shop.headers)).json()
    assert {(s["sku"], s["on_hand"]) for s in stock} == {(v41["sku"], 0), (v42["sku"], 0)}
    page = (await client.get(f"{API}/products/{product['slug']}")).json()
    assert page["in_stock"] is False

    r = await client.patch(
        f"{API}/seller/inventory/{v41['id']}",
        json={"on_hand": 10, "low_stock_threshold": 2},
        headers=shop.headers,
    )
    assert r.status_code == 200
    assert r.json()["available"] == 10
    r = await client.patch(
        f"{API}/seller/inventory/{v41['id']}",
        json={"delta": -9, "note": "продано офлайн"},
        headers=shop.headers,
    )
    assert r.json()["on_hand"] == 1
    assert r.json()["low_stock"] is True

    page = (await client.get(f"{API}/products/{product['slug']}")).json()
    assert page["in_stock"] is True
    assert {v["sku"]: v["in_stock"] for v in page["variants"]} == {
        v41["sku"]: True,
        v42["sku"]: False,
    }
    in_stock = (await client.get(f"{API}/products?store={shop.slug}&size=42&in_stock=true")).json()
    assert in_stock["items"] == []

    low = (await client.get(f"{API}/seller/inventory?low_stock=true", headers=shop.headers)).json()
    assert [s["sku"] for s in low] == [v42["sku"], v41["sku"]]

    moves = (
        await client.get(f"{API}/seller/inventory/{v41['id']}/movements", headers=shop.headers)
    ).json()
    assert [(m["delta"], m["on_hand_after"]) for m in moves] == [(-9, 1), (10, 10)]

    r = await client.patch(
        f"{API}/seller/inventory/{v41['id']}", json={"delta": -5}, headers=shop.headers
    )
    assert r.json()["code"] == "INVENTORY.BELOW_RESERVED"


async def test_stock_of_another_store_is_not_found(client):
    admin, _ = await user_with_role(client, "admin")
    shop = await open_store(client, admin)
    other = await open_store(client, admin)
    _, child, brand = await category_and_brand(client, admin)
    product = await published_product(client, shop, child["id"], brand["id"])
    r = await client.patch(
        f"{API}/seller/inventory/{product['variants'][0]['id']}",
        json={"on_hand": 5},
        headers=other.headers,
    )
    assert r.status_code == 404


async def test_update_needs_something_to_change(client):
    admin, _ = await user_with_role(client, "admin")
    shop = await open_store(client, admin)
    r = await client.patch(
        f"{API}/seller/inventory/00000000-0000-7000-8000-000000000000",
        json={"on_hand": 1, "delta": 1},
        headers=shop.headers,
    )
    assert r.status_code == 422
