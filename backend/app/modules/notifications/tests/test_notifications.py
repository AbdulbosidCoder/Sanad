import pytest

from app.core.db import get_sessionmaker
from app.modules.notifications import service as notifications
from app.modules.notifications.senders import use_sender
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


class Capture:
    def __init__(self):
        self.sent = []

    async def send(self, to, subject, body):
        self.sent.append((to, subject, body))


async def _kinds(client, login):
    page = (await client.get(f"{API}/me/notifications?limit=50", headers=login.auth)).json()
    return [n["kind"] for n in page["items"]], page["items"]


async def test_order_flow_notifies_buyer_and_seller(client):
    admin, _ = await user_with_role(client, "admin")
    _, child, brand = await category_and_brand(client, admin)
    shop = await open_store(client, admin)
    product = await published_product(client, shop, child["id"], brand["id"])
    variant = product["variants"][0]["id"]
    await stock(client, shop, variant, 6)  # threshold is 5: buying 2 leaves 4 -> "running low"
    buyer = await buyer_with_address(client)

    await client.post(
        f"{API}/cart/items", json={"variant_id": variant, "quantity": 2}, headers=buyer.auth
    )
    placed = (await client.post(f"{API}/checkout", json={}, headers={**buyer.auth, **key()})).json()
    r = await client.post(
        f"{API}/payments/{placed['payment']['id']}/confirm",
        json={"outcome": "succeeded"},
        headers=buyer.auth,
    )
    assert r.status_code == 200, r.text

    kinds, items = await _kinds(client, buyer)
    assert kinds == ["order_paid", "order_placed"]
    number = placed["order"]["number"]
    assert number in items[0]["title"]
    assert items[0]["link"] == f"/orders/{placed['order']['id']}"

    seller_kinds, _ = await _kinds(client, shop.owner)
    assert {"store_approved", "store_new_order", "stock_low"} <= set(seller_kinds)

    part = (await client.get(f"{API}/seller/orders", headers=shop.headers)).json()[0]
    r = await client.patch(
        f"{API}/seller/orders/{part['id']}/status",
        json={"status": "confirmed"},
        headers=shop.headers,
    )
    assert r.status_code == 200, r.text
    kinds, items = await _kinds(client, buyer)
    assert kinds[0] == "order_status"
    assert "tasdiqlandi" in items[0]["title"]  # buyer's language is uz by default

    # bell: unread count, then read one / all
    count = (await client.get(f"{API}/me/notifications/unread-count", headers=buyer.auth)).json()
    assert count["unread"] == 3
    r = await client.post(f"{API}/me/notifications/{items[0]['id']}/read", headers=buyer.auth)
    assert r.json()["unread"] == 2
    r = await client.post(f"{API}/me/notifications/read-all", headers=buyer.auth)
    assert r.json()["unread"] == 0
    other, _ = await user_with_role(client)
    r = await client.post(f"{API}/me/notifications/{items[0]['id']}/read", headers=other.auth)
    assert r.status_code == 404

    # e-mails were queued in the same transactions and go out with the worker
    capture = Capture()
    use_sender(capture)
    try:
        async with get_sessionmaker()() as db:
            await notifications.send_pending(db, limit=10_000)
    finally:
        use_sender(None)
    subjects = [s for _, s, _ in capture.sent]
    assert any(number in s for s in subjects)


async def test_preferences_mute_and_email_off(client):
    me, _ = await user_with_role(client)
    r = await client.patch(
        f"{API}/me/notification-preferences",
        json={"email_enabled": False, "muted_kinds": ["order_placed"]},
        headers=me.auth,
    )
    assert r.status_code == 200, r.text
    assert r.json()["email_enabled"] is False and r.json()["muted_kinds"] == ["order_placed"]
    r = await client.patch(
        f"{API}/me/notification-preferences", json={"muted_kinds": ["nope"]}, headers=me.auth
    )
    assert r.status_code == 422


async def test_rejected_application_is_notified(client):
    admin, _ = await user_with_role(client, "admin")
    applicant, _ = await user_with_role(client)
    r = await client.post(
        f"{API}/seller/applications",
        json={"store_name": "Nope Shop", "phone": "+998901112233"},
        headers=applicant.auth,
    )
    r = await client.post(
        f"{API}/admin/seller-applications/{r.json()['id']}/reject",
        json={"note": "Нет документов"},
        headers=admin.auth,
    )
    assert r.status_code == 200, r.text
    kinds, items = await _kinds(client, applicant)
    assert kinds == ["application_rejected"]
    assert items[0]["body"] == "Нет документов"
