import pytest

from tests.factories import API, open_store, uid, user_with_role

pytestmark = pytest.mark.usefixtures("database")


async def test_application_is_reviewed_by_admin_and_creates_a_store(client):
    applicant, _ = await user_with_role(client)
    admin, _ = await user_with_role(client, "admin")
    body = {"store_name": f"Магазин {uid()}", "phone": "+998 90 111-22-33"}

    r = await client.post(f"{API}/seller/applications", json=body, headers=applicant.auth)
    assert r.status_code == 201
    application = r.json()
    assert application["status"] == "submitted"
    again = await client.post(f"{API}/seller/applications", json=body, headers=applicant.auth)
    assert again.json()["code"] == "STORES.APPLICATION_PENDING"

    # Only reviewers may decide.
    denied = await client.post(
        f"{API}/admin/seller-applications/{application['id']}/approve", headers=applicant.auth
    )
    assert denied.status_code == 403
    waiting = await client.get(
        f"{API}/admin/seller-applications?status=submitted&limit=200", headers=admin.auth
    )
    assert application["id"] in [a["id"] for a in waiting.json()]

    r = await client.post(
        f"{API}/admin/seller-applications/{application['id']}/approve",
        json={"note": "ok"},
        headers=admin.auth,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    twice = await client.post(
        f"{API}/admin/seller-applications/{application['id']}/reject", headers=admin.auth
    )
    assert twice.json()["code"] == "STORES.APPLICATION_DECIDED"

    mine = (await client.get(f"{API}/seller/stores", headers=applicant.auth)).json()
    assert len(mine) == 1
    assert mine[0]["role"] == "seller_owner"
    assert "products.write" in mine[0]["permissions"]
    assert mine[0]["store"]["slug"].startswith("magazin-")

    public = await client.get(f"{API}/stores/{mine[0]['store']['slug']}")
    assert public.status_code == 200
    assert "commission_rate" not in public.json()


async def test_seller_endpoints_need_membership_and_hide_other_stores(client):
    admin, _ = await user_with_role(client, "admin")
    shop = await open_store(client, admin)
    other = await open_store(client, admin)
    stranger, _ = await user_with_role(client)

    # No membership at all: the store cannot be picked.
    r = await client.get(f"{API}/seller/store", headers=stranger.auth)
    assert r.json()["code"] == "STORES.STORE_REQUIRED"
    # Someone else's store looks like a missing one.
    r = await client.get(
        f"{API}/seller/store", headers={**shop.owner.auth, "X-Store-Id": other.store_id}
    )
    assert r.status_code == 404

    r = await client.patch(
        f"{API}/seller/store", json={"description": "Новое описание"}, headers=shop.headers
    )
    assert r.status_code == 200
    assert r.json()["description"] == "Новое описание"


async def test_staff_roles_limit_what_members_can_do(client):
    admin, _ = await user_with_role(client, "admin")
    shop = await open_store(client, admin)
    staff, staff_email = await user_with_role(client)

    r = await client.post(
        f"{API}/seller/staff",
        json={"login": staff_email, "role": "seller_staff"},
        headers=shop.headers,
    )
    assert r.status_code == 200
    assert {m["role"] for m in r.json()} == {"seller_owner", "seller_staff"}

    as_staff = {**staff.auth, "X-Store-Id": shop.store_id}
    assert (await client.get(f"{API}/seller/store", headers=as_staff)).status_code == 200
    denied = await client.patch(f"{API}/seller/store", json={"name": "X shop"}, headers=as_staff)
    assert denied.status_code == 403
    assert (await client.get(f"{API}/seller/staff", headers=as_staff)).status_code == 403

    owner_id = (await client.get(f"{API}/me", headers=shop.owner.auth)).json()["id"]
    r = await client.delete(f"{API}/seller/staff/{owner_id}", headers=shop.headers)
    assert r.json()["code"] == "STORES.OWNER_ROLE"
    staff_id = (await client.get(f"{API}/me", headers=staff.auth)).json()["id"]
    r = await client.delete(f"{API}/seller/staff/{staff_id}", headers=shop.headers)
    assert r.status_code == 204
    assert (await client.get(f"{API}/seller/store", headers=as_staff)).status_code == 404


async def test_suspended_store_is_hidden_and_frozen(client):
    admin, _ = await user_with_role(client, "admin")
    shop = await open_store(client, admin)

    r = await client.post(
        f"{API}/admin/stores/{shop.store_id}/suspend",
        json={"reason": "проверка"},
        headers=admin.auth,
    )
    assert r.status_code == 200
    assert (await client.get(f"{API}/stores/{shop.slug}")).status_code == 404
    # Staff can still look, but not change anything.
    assert (await client.get(f"{API}/seller/store", headers=shop.headers)).status_code == 200
    r = await client.patch(f"{API}/seller/store", json={"name": "New"}, headers=shop.headers)
    assert r.json()["code"] == "STORES.STORE_SUSPENDED"

    r = await client.post(f"{API}/admin/stores/{shop.store_id}/reactivate", headers=admin.auth)
    assert r.json()["status"] == "active"
    assert (await client.get(f"{API}/stores/{shop.slug}")).status_code == 200
