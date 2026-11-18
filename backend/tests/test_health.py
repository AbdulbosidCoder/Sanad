import pytest


async def test_live(client):
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.usefixtures("database")
async def test_ready_reports_each_component(client):
    """Needs PostgreSQL and Redis running (CI provides them as services)."""
    r = await client.get("/health/ready")
    body = r.json()
    assert set(body["components"]) == {"database", "redis"}
    assert r.status_code == 200, body
    assert body["status"] == "ok"
