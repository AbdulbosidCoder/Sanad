import pytest

from app.modules.identity.tests.helpers import API, register, unique_phone

pytestmark = pytest.mark.usefixtures("database")


def _address(**overrides: object) -> dict[str, object]:
    return {
        "recipient_name": "Ali Valiyev",
        "phone": unique_phone(),
        "region": "Toshkent",
        "city": "Toshkent",
        "line1": "Amir Temur ko'chasi, 1",
        **overrides,
    }


async def test_first_address_becomes_default_and_default_can_move(client):
    me, _ = await register(client)
    first = (await client.post(f"{API}/me/addresses", json=_address(), headers=me.auth)).json()
    assert first["is_default"] is True

    second = await client.post(
        f"{API}/me/addresses", json=_address(city="Samarqand", is_default=True), headers=me.auth
    )
    assert second.status_code == 201
    listed = (await client.get(f"{API}/me/addresses", headers=me.auth)).json()
    assert [a["is_default"] for a in listed] == [True, False]
    assert listed[0]["city"] == "Samarqand"

    r = await client.patch(
        f"{API}/me/addresses/{first['id']}", json={"is_default": True}, headers=me.auth
    )
    assert r.status_code == 200
    listed = (await client.get(f"{API}/me/addresses", headers=me.auth)).json()
    assert [a["id"] for a in listed if a["is_default"]] == [first["id"]]


async def test_deleting_the_default_promotes_another(client):
    me, _ = await register(client)
    first = (await client.post(f"{API}/me/addresses", json=_address(), headers=me.auth)).json()
    second = (await client.post(f"{API}/me/addresses", json=_address(), headers=me.auth)).json()

    assert (
        await client.delete(f"{API}/me/addresses/{first['id']}", headers=me.auth)
    ).status_code == 204
    listed = (await client.get(f"{API}/me/addresses", headers=me.auth)).json()
    assert [(a["id"], a["is_default"]) for a in listed] == [(second["id"], True)]


async def test_line2_can_be_cleared_and_other_fields_kept(client):
    me, _ = await register(client)
    created = (
        await client.post(f"{API}/me/addresses", json=_address(line2="2-qavat"), headers=me.auth)
    ).json()
    r = await client.patch(
        f"{API}/me/addresses/{created['id']}",
        json={"line2": None, "recipient_name": None},
        headers=me.auth,
    )
    assert r.status_code == 200
    assert r.json()["line2"] is None
    assert r.json()["recipient_name"] == "Ali Valiyev"


async def test_other_users_addresses_are_invisible(client):
    alice, _ = await register(client)
    bob, _ = await register(client)
    bobs = (await client.post(f"{API}/me/addresses", json=_address(), headers=bob.auth)).json()

    assert (await client.get(f"{API}/me/addresses", headers=alice.auth)).json() == []
    patch = await client.patch(
        f"{API}/me/addresses/{bobs['id']}", json={"city": "X"}, headers=alice.auth
    )
    assert patch.status_code == 404
    assert patch.json()["code"] == "IDENTITY.ADDRESS_NOT_FOUND"
    delete = await client.delete(f"{API}/me/addresses/{bobs['id']}", headers=alice.auth)
    assert delete.status_code == 404


async def test_address_input_is_validated(client):
    me, _ = await register(client)
    bad_phone = await client.post(
        f"{API}/me/addresses", json=_address(phone="12345"), headers=me.auth
    )
    assert bad_phone.status_code == 422
    extra = await client.post(
        f"{API}/me/addresses",
        json=_address(user_id="00000000-0000-0000-0000-000000000000"),
        headers=me.auth,
    )
    assert extra.status_code == 422
