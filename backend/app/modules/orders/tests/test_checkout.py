import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.db import get_sessionmaker
from app.modules.orders import service as orders
from app.modules.payments.service import sign_fake_webhook
from tests.factories import (
    API,
    buyer_with_address,
    category_and_brand,
    key,
    open_store,
    published_product,
    stock,
    user_with_role,
)

pytestmark = pytest.mark.usefixtures("database")


@pytest.fixture
async def market(client):
    """Two stores with one stocked product each, and a buyer with an address."""
    admin, _ = await user_with_role(client, "admin")
    _, child, brand = await category_and_brand(client, admin)
    a = await open_store(client, admin)
    b = await open_store(client, admin)
    pa = await published_product(client, a, child["id"], brand["id"], price="100000")
    pb = await published_product(client, b, child["id"], brand["id"], sizes=("M",), price="50000")
    await stock(client, a, pa["variants"][0]["id"], 5)
    await stock(client, b, pb["variants"][0]["id"], 3)
    buyer = await buyer_with_address(client)
    return {"admin": admin, "a": a, "b": b, "pa": pa, "pb": pb, "buyer": buyer}


async def _fill_cart(client, m, qa=2, qb=1):
    for variant, q in ((m["pa"]["variants"][0]["id"], qa), (m["pb"]["variants"][0]["id"], qb)):
        r = await client.post(
            f"{API}/cart/items",
            json={"variant_id": variant, "quantity": q},
            headers=m["buyer"].auth,
        )
        assert r.status_code == 200, r.text
    return r.json()


async def _available(client, shop, variant_id):
    rows = (await client.get(f"{API}/seller/inventory", headers=shop.headers)).json()
    row = next(s for s in rows if s["variant_id"] == variant_id)
    return row["on_hand"], row["reserved"]


async def _checkout(client, m, headers=None):
    r = await client.post(
        f"{API}/checkout", json={}, headers={**m["buyer"].auth, **(headers or key())}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _pay(client, m, payment_id, outcome="succeeded"):
    r = await client.post(
        f"{API}/payments/{payment_id}/confirm", json={"outcome": outcome}, headers=m["buyer"].auth
    )
    assert r.status_code == 200, r.text


async def test_cart_is_grouped_by_seller_and_checks_stock(client, market):
    m = market
    cart = await _fill_cart(client, m)
    assert len(cart["groups"]) == 2
    assert cart["total"] == "250000.00"
    assert cart["can_checkout"] is True
    r = await client.post(
        f"{API}/cart/items",
        json={"variant_id": m["pb"]["variants"][0]["id"], "quantity": 5},
        headers=m["buyer"].auth,
    )
    assert r.json()["code"] == "CART.NOT_ENOUGH_STOCK"


async def test_checkout_splits_per_seller_holds_stock_and_is_idempotent(client, market):
    m = market
    await _fill_cart(client, m)
    preview = (
        await client.post(f"{API}/checkout/preview", json={}, headers=m["buyer"].auth)
    ).json()
    assert preview["total"] == "250000.00"
    assert preview["payment_methods"] == ["fake"]

    headers = key()
    first = await _checkout(client, m, headers)
    order = first["order"]
    assert order["payment_status"] == "pending"
    assert len(order["seller_orders"]) == 2
    assert first["payment"]["is_test"] is True
    assert first["next_step"].endswith("/confirm")
    # A retry with the same key gives the same order, not a second one.
    again = await _checkout(client, m, headers)
    assert again["order"]["id"] == order["id"]

    assert await _available(client, m["a"], m["pa"]["variants"][0]["id"]) == (5, 2)
    cart = (await client.get(f"{API}/cart", headers=m["buyer"].auth)).json()
    assert cart["item_count"] == 0

    await _pay(client, m, first["payment"]["id"])
    paid = (await client.get(f"{API}/orders/{order['id']}", headers=m["buyer"].auth)).json()
    assert paid["payment_status"] == "paid"
    assert await _available(client, m["a"], m["pa"]["variants"][0]["id"]) == (3, 0)

    # Seller A sees only its part, with the address to ship to.
    seller_orders = (await client.get(f"{API}/seller/orders", headers=m["a"].headers)).json()
    assert len(seller_orders) == 1
    part = seller_orders[0]
    assert part["subtotal"] == "200000.00"
    assert part["commission"] == "20000.00"
    assert part["shipping_address"]["city"] == "Toshkent"

    for status, extra in (
        ("confirmed", {}),
        ("shipped", {"tracking_number": "UZ123"}),
        ("delivered", {}),
    ):
        r = await client.patch(
            f"{API}/seller/orders/{part['id']}/status",
            json={"status": status, **extra},
            headers=m["a"].headers,
        )
        assert r.status_code == 200, r.text
    tracked = (await client.get(f"{API}/orders/{order['id']}", headers=m["buyer"].auth)).json()
    assert tracked["status"] == "partially_fulfilled"
    mine = next(s for s in tracked["seller_orders"] if s["id"] == part["id"])
    assert [h["to_status"] for h in mine["history"]] == ["new", "confirmed", "shipped", "delivered"]
    assert mine["tracking_number"] == "UZ123"

    # Store B cannot touch store A's part; going backwards is not allowed.
    r = await client.patch(
        f"{API}/seller/orders/{part['id']}/status",
        json={"status": "shipped"},
        headers=m["b"].headers,
    )
    assert r.status_code == 404
    r = await client.patch(
        f"{API}/seller/orders/{part['id']}/status",
        json={"status": "shipped"},
        headers=m["a"].headers,
    )
    assert r.json()["code"] == "ORDERS.BAD_TRANSITION"


async def test_failed_payment_releases_stock_and_refills_cart(client, market):
    m = market
    await _fill_cart(client, m)
    out = await _checkout(client, m)
    await _pay(client, m, out["payment"]["id"], "failed")
    order = (await client.get(f"{API}/orders/{out['order']['id']}", headers=m["buyer"].auth)).json()
    assert (order["status"], order["payment_status"]) == ("cancelled", "failed")
    assert await _available(client, m["a"], m["pa"]["variants"][0]["id"]) == (5, 0)
    cart = (await client.get(f"{API}/cart", headers=m["buyer"].auth)).json()
    assert cart["item_count"] == 3


async def test_seller_cannot_confirm_before_payment(client, market):
    m = market
    await _fill_cart(client, m)
    await _checkout(client, m)
    part = (await client.get(f"{API}/seller/orders", headers=m["a"].headers)).json()[0]
    r = await client.patch(
        f"{API}/seller/orders/{part['id']}/status",
        json={"status": "confirmed"},
        headers=m["a"].headers,
    )
    assert r.json()["code"] == "ORDERS.NOT_PAID"


async def test_out_of_stock_at_checkout_changes_nothing(client, market):
    m = market
    await _fill_cart(client, m)
    await stock(client, m["b"], m["pb"]["variants"][0]["id"], 0)
    r = await client.post(f"{API}/checkout", json={}, headers={**m["buyer"].auth, **key()})
    assert r.json()["code"] == "CART.CART_HAS_PROBLEMS"
    assert (await client.get(f"{API}/orders", headers=m["buyer"].auth)).json() == []
    assert await _available(client, m["a"], m["pa"]["variants"][0]["id"]) == (5, 0)


async def test_buyer_cancels_paid_order_and_gets_money_back(client, market):
    m = market
    await _fill_cart(client, m)
    out = await _checkout(client, m)
    await _pay(client, m, out["payment"]["id"])
    r = await client.post(
        f"{API}/orders/{out['order']['id']}/cancel",
        json={"reason": "передумал"},
        headers=m["buyer"].auth,
    )
    assert r.status_code == 200, r.text
    order = r.json()
    assert (order["status"], order["payment_status"]) == ("cancelled", "refunded")
    assert await _available(client, m["a"], m["pa"]["variants"][0]["id"]) == (5, 0)

    finance, _ = await user_with_role(client, "finance")
    ledger = (
        await client.get(f"{API}/admin/ledger?store_id={m['a'].store_id}", headers=finance.auth)
    ).json()
    assert sorted(e["type"] for e in ledger) == [
        "commission",
        "commission_refund",
        "refund",
        "sale",
    ]
    assert sum(float(e["amount"]) for e in ledger) == 0


async def test_return_needs_finance_approval_by_another_person(client, market):
    m = market
    await client.post(
        f"{API}/cart/items",
        json={"variant_id": m["pa"]["variants"][0]["id"], "quantity": 2},
        headers=m["buyer"].auth,
    )
    out = await _checkout(client, m)
    await _pay(client, m, out["payment"]["id"])
    part = out["order"]["seller_orders"][0]
    for status in ("confirmed", "shipped", "delivered"):
        await client.patch(
            f"{API}/seller/orders/{part['id']}/status",
            json={"status": status},
            headers=m["a"].headers,
        )
    item = part["items"][0]
    r = await client.post(
        f"{API}/orders/{out['order']['id']}/items/{item['id']}/return",
        json={"quantity": 1, "reason": "не подошёл размер"},
        headers=m["buyer"].auth,
    )
    assert r.status_code == 201, r.text
    ret = r.json()
    for action in ("approve", "receive"):
        r = await client.patch(
            f"{API}/seller/returns/{ret['id']}", json={"action": action}, headers=m["a"].headers
        )
        assert r.status_code == 200, r.text
    refund_id = r.json()["refund_id"]
    assert await _available(client, m["a"], m["pa"]["variants"][0]["id"]) == (4, 0)

    finance, _ = await user_with_role(client, "finance")
    r = await client.post(f"{API}/admin/refunds/{refund_id}/approve", headers=finance.auth)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    order = (await client.get(f"{API}/orders/{out['order']['id']}", headers=m["buyer"].auth)).json()
    assert order["payment_status"] == "partially_refunded"
    returns = (await client.get(f"{API}/orders/returns", headers=m["buyer"].auth)).json()
    assert returns[0]["status"] == "refunded"


async def test_guest_cart_merges_after_sign_in(client, market):
    m = market
    token = {"X-Cart-Token": uuid.uuid4().hex + uuid.uuid4().hex}
    r = await client.post(
        f"{API}/cart/items",
        json={"variant_id": m["pb"]["variants"][0]["id"], "quantity": 1},
        headers=token,
    )
    assert r.status_code == 200, r.text
    assert (await client.get(f"{API}/cart", headers=token)).json()["item_count"] == 1
    merged = await client.post(f"{API}/cart/merge", headers={**m["buyer"].auth, **token})
    assert merged.json()["item_count"] == 1
    assert (await client.get(f"{API}/cart", headers=token)).json()["item_count"] == 0


async def test_signed_webhook_pays_once(client, market):
    m = market
    await _fill_cart(client, m)
    out = await _checkout(client, m)
    async with get_sessionmaker()() as db:
        pid = await db.scalar(
            text("SELECT provider_payment_id FROM payments WHERE id = :id"),
            {"id": out["payment"]["id"]},
        )
    body = json.dumps(
        {"event_id": uuid.uuid4().hex, "provider_payment_id": pid, "status": "succeeded"}
    ).encode()
    bad = await client.post(
        f"{API}/webhooks/payments/fake", content=body, headers={"X-Fake-Signature": "0" * 64}
    )
    assert bad.status_code == 400
    good = {"X-Fake-Signature": sign_fake_webhook(body)}
    r = await client.post(f"{API}/webhooks/payments/fake", content=body, headers=good)
    assert r.json() == {"result": "applied"}
    r = await client.post(f"{API}/webhooks/payments/fake", content=body, headers=good)
    assert r.json() == {"result": "duplicate"}
    order = (await client.get(f"{API}/orders/{out['order']['id']}", headers=m["buyer"].auth)).json()
    assert order["payment_status"] == "paid"


async def test_unpaid_orders_expire(client, market):
    m = market
    await _fill_cart(client, m)
    out = await _checkout(client, m)
    async with get_sessionmaker()() as db:
        await db.execute(
            text("UPDATE stock_reservations SET expires_at = :t WHERE order_id = :o"),
            {"t": datetime.now(UTC) - timedelta(minutes=1), "o": out["order"]["id"]},
        )
        await db.commit()
    assert await orders.expire_unpaid() >= 1
    order = (await client.get(f"{API}/orders/{out['order']['id']}", headers=m["buyer"].auth)).json()
    assert order["status"] == "cancelled"
    assert order["payments"][0]["status"] == "cancelled"
    assert await _available(client, m["a"], m["pa"]["variants"][0]["id"]) == (5, 0)
