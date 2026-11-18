import pytest

from tests.factories import API, user_with_role

pytestmark = pytest.mark.usefixtures("database")


async def _id(client, login):
    return (await client.get(f"{API}/me", headers=login.auth)).json()["id"]


async def test_ticket_conversation(client):
    customer, _ = await user_with_role(client)
    agent, _ = await user_with_role(client, "support_agent")
    other_agent, _ = await user_with_role(client, "support_agent")
    lead, _ = await user_with_role(client, "support_lead")

    r = await client.post(
        f"{API}/support/tickets",
        json={"subject": "Не пришёл заказ", "category": "payment", "message": "Деньги списали"},
        headers=customer.auth,
    )
    assert r.status_code == 201, r.text
    ticket = r.json()
    assert ticket["priority"] == "high" and ticket["status"] == "open"
    tid = ticket["id"]

    queue = (
        await client.get(f"{API}/admin/support/tickets?unassigned=true", headers=agent.auth)
    ).json()
    assert tid in [t["id"] for t in queue]
    assert (
        await client.get(f"{API}/admin/support/tickets", headers=customer.auth)
    ).status_code == 403

    r = await client.post(
        f"{API}/admin/support/tickets/{tid}/messages",
        json={"body": "Проверю платёж", "internal": True},
        headers=agent.auth,
    )
    assert r.json()["assignee_id"] == await _id(client, agent)  # first answer takes it
    assert r.json()["status"] == "open"  # a note is not an answer
    await client.post(
        f"{API}/admin/support/tickets/{tid}/messages",
        json={"body": "Платёж вернётся в течение суток"},
        headers=agent.auth,
    )

    mine = (await client.get(f"{API}/support/tickets/{tid}", headers=customer.auth)).json()
    assert mine["status"] == "answered"
    assert [m["body"] for m in mine["messages"]] == [
        "Деньги списали",
        "Платёж вернётся в течение суток",
    ]
    bell = (await client.get(f"{API}/me/notifications", headers=customer.auth)).json()
    assert bell["items"][0]["kind"] == "ticket_replied"

    # assigned to someone else: another agent does not see it, a lead does
    r = await client.get(f"{API}/admin/support/tickets/{tid}", headers=other_agent.auth)
    assert r.status_code == 404
    staff = (await client.get(f"{API}/admin/support/tickets/{tid}", headers=lead.auth)).json()
    assert len(staff["messages"]) == 3 and staff["customer_name"] is not None

    r = await client.post(
        f"{API}/admin/support/tickets/{tid}/assign",
        json={"assignee_id": await _id(client, other_agent)},
        headers=agent.auth,
    )
    assert r.status_code == 403
    r = await client.post(
        f"{API}/admin/support/tickets/{tid}/assign",
        json={"assignee_id": await _id(client, other_agent)},
        headers=lead.auth,
    )
    assert r.status_code == 200
    assert (
        await client.get(f"{API}/admin/support/tickets/{tid}", headers=other_agent.auth)
    ).status_code == 200

    await client.patch(
        f"{API}/admin/support/tickets/{tid}", json={"status": "resolved"}, headers=lead.auth
    )
    r = await client.post(
        f"{API}/support/tickets/{tid}/messages",
        json={"body": "Не вернулись"},
        headers=customer.auth,
    )
    assert r.json()["status"] == "open"  # the customer reopened it
    r = await client.post(f"{API}/support/tickets/{tid}/close", headers=customer.auth)
    assert r.json()["status"] == "closed"

    stranger, _ = await user_with_role(client)
    assert (
        await client.get(f"{API}/support/tickets/{tid}", headers=stranger.auth)
    ).status_code == 404


async def test_ticket_order_must_be_own(client):
    customer, _ = await user_with_role(client)
    r = await client.post(
        f"{API}/support/tickets",
        json={
            "subject": "Заказ",
            "category": "order",
            "message": "?",
            "order_id": "01900000-0000-7000-8000-000000000000",
        },
        headers=customer.auth,
    )
    assert r.status_code == 404
