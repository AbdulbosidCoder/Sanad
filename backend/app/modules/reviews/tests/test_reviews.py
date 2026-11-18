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


@pytest.fixture
async def bought(client):
    admin, _ = await user_with_role(client, "admin")
    _, child, brand = await category_and_brand(client, admin)
    shop = await open_store(client, admin)
    product = await published_product(client, shop, child["id"], brand["id"])
    await stock(client, shop, product["variants"][0]["id"], 10)
    buyer = await buyer_with_address(client)
    await delivered_purchase(client, shop, product["variants"][0]["id"], buyer)
    return {"admin": admin, "shop": shop, "product": product, "buyer": buyer}


async def test_only_buyers_who_received_it_can_review(client, bought):
    product = bought["product"]
    url = f"{API}/products/{product['id']}/reviews"
    stranger, _ = await user_with_role(client)
    r = await client.post(url, json={"rating": 5}, headers=stranger.auth)
    assert r.status_code == 403 and r.json()["code"] == "REVIEWS.NOT_PURCHASED"
    check = (await client.get(f"{url}/can-review", headers=stranger.auth)).json()
    assert check["reason"] == "not_purchased"

    buyer = bought["buyer"]
    assert (await client.get(f"{url}/can-review", headers=buyer.auth)).json()["can_review"]
    r = await client.post(
        url, json={"rating": 4, "text": "Хорошие, маломерят", "fit": "small"}, headers=buyer.auth
    )
    assert r.status_code == 201, r.text
    review = r.json()
    assert review["verified_purchase"] and review["author"]
    again = await client.post(url, json={"rating": 5}, headers=buyer.auth)
    assert again.status_code == 409

    page = (await client.get(f"{API}/products/{product['slug']}")).json()
    assert page["rating_avg"] == "4.00" and page["rating_count"] == 1
    summary = (await client.get(f"{url}/summary")).json()
    assert summary["distribution"]["4"] == 1 and summary["fit"] == {"small": 1}

    r = await client.patch(
        f"{API}/me/reviews/{review['id']}", json={"rating": 2}, headers=buyer.auth
    )
    assert r.json()["rating"] == 2
    page = (await client.get(f"{API}/products/{product['slug']}")).json()
    assert page["rating_avg"] == "2.00"


async def test_seller_reply_and_moderation(client, bought):
    product, shop, buyer, admin = (
        bought["product"],
        bought["shop"],
        bought["buyer"],
        bought["admin"],
    )
    url = f"{API}/products/{product['id']}/reviews"
    review = (
        await client.post(url, json={"rating": 1, "text": "Плохо"}, headers=buyer.auth)
    ).json()

    unanswered = (
        await client.get(f"{API}/seller/reviews?unanswered=true", headers=shop.headers)
    ).json()
    assert [r["id"] for r in unanswered["items"]] == [review["id"]]
    r = await client.put(
        f"{API}/seller/reviews/{review['id']}/reply",
        json={"text": "Свяжитесь с нами"},
        headers=shop.headers,
    )
    assert r.status_code == 200 and r.json()["seller_reply"] == "Свяжитесь с нами"

    other = await open_store(client, admin)
    r = await client.put(
        f"{API}/seller/reviews/{review['id']}/reply", json={"text": "x"}, headers=other.headers
    )
    assert r.status_code == 404

    assert (
        await client.post(
            f"{API}/admin/reviews/{review['id']}/hide", json={"reason": "spam"}, headers=buyer.auth
        )
    ).status_code == 403
    r = await client.post(
        f"{API}/admin/reviews/{review['id']}/hide",
        json={"reason": "Оскорбления"},
        headers=admin.auth,
    )
    assert r.status_code == 200 and r.json()["status"] == "hidden"
    assert (await client.get(url)).json()["items"] == []
    page = (await client.get(f"{API}/products/{product['slug']}")).json()
    assert page["rating_count"] == 0

    mine = (await client.get(f"{API}/me/reviews", headers=buyer.auth)).json()
    assert mine[0]["status"] == "hidden"
