import pytest

from tests.factories import API, category_and_brand, open_store, published_product, user_with_role

pytestmark = pytest.mark.usefixtures("database")


@pytest.fixture
async def products(client):
    admin, _ = await user_with_role(client, "admin")
    _, child, brand = await category_and_brand(client, admin)
    shop = await open_store(client, admin)
    return [await published_product(client, shop, child["id"], brand["id"]) for _ in range(3)]


async def test_favorites(client, products):
    buyer, _ = await user_with_role(client)
    a, b, c = products
    for p in (a, b, a):  # adding twice is fine
        r = await client.put(f"{API}/me/favorites/{p['id']}", headers=buyer.auth)
        assert r.status_code == 200 and r.json()["favorite"] is True
    page = (await client.get(f"{API}/me/favorites", headers=buyer.auth)).json()
    assert [p["id"] for p in page["items"]] == [b["id"], a["id"]]  # newest first

    r = await client.get(
        f"{API}/me/favorites/flags",
        params={"product_id": [a["id"], c["id"]]},
        headers=buyer.auth,
    )
    assert [f["favorite"] for f in r.json()] == [True, False]

    await client.delete(f"{API}/me/favorites/{a['id']}", headers=buyer.auth)
    page = (await client.get(f"{API}/me/favorites", headers=buyer.auth)).json()
    assert [p["id"] for p in page["items"]] == [b["id"]]

    assert (await client.get(f"{API}/me/favorites")).status_code == 401
    missing = "01900000-0000-7000-8000-000000000000"
    r = await client.put(f"{API}/me/favorites/{missing}", headers=buyer.auth)
    assert r.status_code == 404


async def test_views_are_counted_once_per_window(client, products):
    a, b, _ = products
    buyer, _ = await user_with_role(client)
    first = await client.post(f"{API}/products/{a['id']}/views", headers=buyer.auth)
    again = await client.post(f"{API}/products/{a['id']}/views", headers=buyer.auth)
    assert first.json()["counted"] is True and again.json()["counted"] is False
    await client.post(f"{API}/products/{b['id']}/views", headers=buyer.auth)

    viewed = (await client.get(f"{API}/me/viewed", headers=buyer.auth)).json()
    assert [p["id"] for p in viewed] == [b["id"], a["id"]]

    guest = {"X-Device-Id": "device-123456789"}
    assert (await client.post(f"{API}/products/{a['id']}/views", headers=guest)).json()["counted"]
    assert not (await client.post(f"{API}/products/{a['id']}/views", headers=guest)).json()[
        "counted"
    ]
