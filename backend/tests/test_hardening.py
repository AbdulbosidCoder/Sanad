import pytest

from app.core import ratelimit
from app.core.config import get_settings
from tests.factories import API


@pytest.fixture
def limits_on():
    settings = get_settings()
    settings.rate_limit_enabled = True
    ratelimit.reset_memory()
    yield
    settings.rate_limit_enabled = False
    ratelimit.reset_memory()


async def test_security_headers(client):
    r = await client.get("/health/live")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in r.headers  # only in prod
    me = await client.get(f"{API}/me")
    assert me.headers["Cache-Control"] == "no-store"


async def test_big_bodies_are_rejected(client):
    r = await client.post(
        f"{API}/auth/login",
        content=b"{" + b" " * 1_100_000 + b"}",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413 and r.json()["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.usefixtures("database", "limits_on")
async def test_login_is_rate_limited_per_ip(client):
    body = {"login": "nobody@example.com", "password": "wrong-password"}
    for _ in range(20):
        r = await client.post(f"{API}/auth/login", json=body)
        assert r.status_code == 401
    r = await client.post(f"{API}/auth/login", json=body)
    assert r.status_code == 429
    assert r.json()["code"] == "PLATFORM.RATE_LIMITED"
    assert int(r.headers["Retry-After"]) > 0


@pytest.mark.usefixtures("database")
async def test_ops_dashboard(client):
    from tests.factories import user_with_role

    dev, _ = await user_with_role(client, "developer")
    r = await client.get(f"{API}/admin/ops", headers=dev.auth)
    assert r.status_code == 200 and r.json()["database"] is True
    assert {q["name"] for q in r.json()["queues"]} == {"translations", "emails"}
    r = await client.post(f"{API}/admin/ops/queues/emails/retry", headers=dev.auth)
    assert r.status_code == 200 and r.json()["queue"] == "emails"
    buyer, _ = await user_with_role(client)
    assert (await client.get(f"{API}/admin/ops", headers=buyer.auth)).status_code == 403
