import pytest

from app.modules.identity.tests.helpers import API, login
from app.seed import PASSWORD, run

pytestmark = pytest.mark.usefixtures("database")


async def test_demo_data_can_be_loaded_twice_and_is_usable(client):
    assert await run(if_empty=True) == 0
    assert await run(if_empty=True) == 0  # second run changes nothing

    r = await login(client, "seller1@example.com", PASSWORD)
    assert r.status_code == 200
    seller = {"Authorization": f"Bearer {r.json()['access_token']}"}
    stores = (await client.get(f"{API}/seller/stores", headers=seller)).json()
    assert [s["store"]["name"] for s in stores] == ["Sneaker Lab"]
    stock = (await client.get(f"{API}/seller/inventory?low_stock=true", headers=seller)).json()
    assert stock, "demo data has low-stock variants"

    products = (await client.get(f"{API}/products?store=sneaker-lab")).json()["items"]
    assert len(products) == 4
    page = (await client.get(f"{API}/products/{products[0]['slug']}")).json()
    assert page["photo_coverage"]["complete"] is True
