import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import get_sessionmaker
from tests.factories import API, PASSWORD, user_with_role

pytestmark = pytest.mark.usefixtures("database")


async def _id(client, login):
    return (await client.get(f"{API}/me", headers=login.auth)).json()["id"]


async def test_block_user_ends_sessions_and_is_audited(client):
    admin, _ = await user_with_role(client, "admin")
    victim, email = await user_with_role(client)
    victim_id = await _id(client, victim)

    found = (await client.get(f"{API}/admin/users", params={"q": email}, headers=admin.auth)).json()
    assert [u["id"] for u in found] == [victim_id] and "customer" in found[0]["roles"]

    r = await client.post(
        f"{API}/admin/users/{victim_id}/block", json={"reason": "мошенничество"}, headers=admin.auth
    )
    assert r.status_code == 200 and r.json()["status"] == "blocked"
    assert (await client.get(f"{API}/me", headers=victim.auth)).status_code == 401
    r = await client.post(f"{API}/auth/login", json={"login": email, "password": PASSWORD})
    assert r.status_code == 403

    me = await _id(client, admin)
    r = await client.post(
        f"{API}/admin/users/{me}/block", json={"reason": "test"}, headers=admin.auth
    )
    assert r.status_code == 409

    log = (
        await client.get(f"{API}/admin/audit", params={"target_id": victim_id}, headers=admin.auth)
    ).json()
    assert log[0]["action"] == "users.block" and log[0]["actor_id"] == me
    assert log[0]["data"]["reason"] == "мошенничество"

    r = await client.post(f"{API}/admin/users/{victim_id}/unblock", headers=admin.auth)
    assert r.json()["status"] == "active"
    verify = (await client.get(f"{API}/admin/audit/verify", headers=admin.auth)).json()
    assert verify["ok"] is True and verify["checked"] >= 2


async def test_audit_rows_cannot_be_changed(client):
    admin, _ = await user_with_role(client, "admin")
    victim, _ = await user_with_role(client)
    await client.post(
        f"{API}/admin/users/{await _id(client, victim)}/block",
        json={"reason": "test"},
        headers=admin.auth,
    )
    async with get_sessionmaker()() as db:
        with pytest.raises(DBAPIError, match="append-only"):
            await db.execute(text("UPDATE audit_logs SET action = 'x'"))
        await db.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            await db.execute(text("DELETE FROM audit_logs"))


async def test_roles_need_rbac_manage_and_keep_a_super_admin(client):
    admin, _ = await user_with_role(client, "admin")
    boss, _ = await user_with_role(client, "super_admin")
    target, _ = await user_with_role(client)
    target_id = await _id(client, target)

    url = f"{API}/admin/users/{target_id}/roles/support_agent"
    assert (await client.put(url, headers=admin.auth)).status_code == 403  # admin lacks rbac.manage
    r = await client.put(url, headers=boss.auth)
    assert r.status_code == 200 and "support_agent" in r.json()["roles"]
    r = await client.delete(url, headers=boss.auth)
    assert "support_agent" not in r.json()["roles"]

    r = await client.put(f"{API}/admin/users/{target_id}/roles/seller_owner", headers=boss.auth)
    assert r.status_code == 400  # store roles go through stores
    r = await client.delete(f"{API}/admin/users/{target_id}/roles/customer", headers=boss.auth)
    assert r.status_code == 409

    finance, _ = await user_with_role(client, "finance")
    log = (await client.get(f"{API}/admin/audit", headers=finance.auth)).json()
    assert all(
        e["action"].split(".")[0] in ("payments", "refunds", "returns", "orders") for e in log
    )
    assert (await client.get(f"{API}/admin/audit/verify", headers=finance.auth)).status_code == 403
    buyer, _ = await user_with_role(client)
    assert (await client.get(f"{API}/admin/audit", headers=buyer.auth)).status_code == 403
