import pytest

from tests.factories import (
    API,
    category_and_brand,
    open_store,
    published_product,
    stock,
    user_with_role,
)

pytestmark = pytest.mark.usefixtures("database")


async def test_home_and_product_blocks(client):
    admin, _ = await user_with_role(client, "admin")
    _, child, brand = await category_and_brand(client, admin)
    shop = await open_store(client, admin)
    products = []
    for _ in range(4):
        p = await published_product(client, shop, child["id"], brand["id"])
        await stock(client, shop, p["variants"][0]["id"], 3)
        products.append(p)
    a, b, c, _ = products

    # two buyers who opened a also opened b -> "people also viewed" on a's page shows b
    buyers = [(await user_with_role(client))[0] for _ in range(2)]
    for buyer in buyers:
        for p in (a, b):
            await client.post(f"{API}/products/{p['id']}/views", headers=buyer.auth)
    await client.post(f"{API}/products/{c['id']}/views", headers=buyers[0].auth)

    home = (await client.get(f"{API}/home?lang=en")).json()
    keys = [blk["key"] for blk in home["blocks"]]
    assert "new" in keys and "trending" in keys
    new = next(blk for blk in home["blocks"] if blk["key"] == "new")
    assert new["title"] == "New arrivals"
    assert home["categories"] and home["brands"]

    mine = (await client.get(f"{API}/home", headers=buyers[1].auth)).json()
    for_you = next(blk for blk in mine["blocks"] if blk["key"] == "for_you")
    assert c["id"] in [p["id"] for p in for_you["items"]]  # seen by a buyer like them

    blocks = (await client.get(f"{API}/products/{a['id']}/recommendations")).json()
    also = next(blk for blk in blocks if blk["key"] == "also_viewed")
    assert also["items"][0]["id"] == b["id"]
    similar = next(blk for blk in blocks if blk["key"] == "similar")
    assert a["id"] not in [p["id"] for p in similar["items"]]
