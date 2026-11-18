import pytest

from tests.factories import (
    API,
    buyer_with_address,
    category_and_brand,
    delivered_purchase,
    open_store,
    published_product,
    stock,
    user_with_role,
)

pytestmark = pytest.mark.usefixtures("database")


async def test_seller_summary_and_products(client):
    admin, _ = await user_with_role(client, "admin")
    _, child, brand = await category_and_brand(client, admin)
    shop = await open_store(client, admin)
    hit = await published_product(client, shop, child["id"], brand["id"], price="100000")
    quiet = await published_product(client, shop, child["id"], brand["id"])
    await stock(client, shop, hit["variants"][0]["id"], 7)  # 7 - 3 = 4 <= 5: low stock

    buyers = [await buyer_with_address(client) for _ in range(2)]
    for b in buyers:
        await client.post(f"{API}/products/{hit['id']}/views", headers=b.auth)
    await client.post(f"{API}/products/{quiet['id']}/views", headers=buyers[0].auth)
    await delivered_purchase(client, shop, hit["variants"][0]["id"], buyers[0], quantity=2)
    await delivered_purchase(client, shop, hit["variants"][0]["id"], buyers[1], quantity=1)

    s = (await client.get(f"{API}/seller/analytics/summary?days=7", headers=shop.headers)).json()
    assert s["orders"] == 2
    assert s["revenue"] == "300000.00"
    assert s["commission"] == "30000.00" and s["net"] == "270000.00"
    assert s["average_order"] == "150000.00"
    assert s["views"] == 3 and s["unique_viewers"] == 2
    assert s["conversion_pct"] == 100.0
    assert s["orders_by_status"] == {"delivered": 2}
    assert s["low_stock_variants"] >= 1
    assert len(s["by_day"]) in (8, 9) and sum(d["orders"] for d in s["by_day"]) == 2
    assert s["change"]["revenue_pct"] is None  # nothing in the previous week

    rows = (await client.get(f"{API}/seller/analytics/products", headers=shop.headers)).json()
    assert rows[0]["product_id"] == hit["id"]
    assert (rows[0]["units"], rows[0]["views"]) == (3, 2)
    assert rows[1]["product_id"] == quiet["id"] and rows[1]["units"] == 0

    buyer = buyers[0]
    r = await client.get(
        f"{API}/seller/analytics/summary", headers={**buyer.auth, "X-Store-Id": shop.store_id}
    )
    assert r.status_code == 404  # not their store
