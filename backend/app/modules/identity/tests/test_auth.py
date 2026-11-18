import pytest

from app.modules.identity.api import REFRESH_COOKIE, REFRESH_COOKIE_PATH
from app.modules.identity.tests.helpers import (
    API,
    PASSWORD,
    Login,
    login,
    login_from,
    logout,
    refresh,
    register,
    unique_email,
    unique_phone,
    with_cookies,
)

pytestmark = pytest.mark.usefixtures("database")


# ---------------------------------------------------------------- registration


async def test_register_signs_in_as_customer(client):
    r = await client.post(
        f"{API}/auth/register",
        json={"email": unique_email(), "password": PASSWORD, "full_name": "Ali", "locale": "ru"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["next_step"] is None
    assert "refresh_token" not in body  # only in the HttpOnly cookie

    set_cookie = r.headers.get_list("set-cookie")
    refresh_cookie = next(c for c in set_cookie if c.startswith(f"{REFRESH_COOKIE}="))
    assert "HttpOnly" in refresh_cookie
    assert f"Path={REFRESH_COOKIE_PATH}" in refresh_cookie
    assert "SameSite=lax" in refresh_cookie

    me = await client.get(f"{API}/me", headers=login_from(r).auth)
    assert me.status_code == 200
    data = me.json()
    assert data["full_name"] == "Ali"
    assert data["locale"] == "ru"
    assert data["roles"] == ["customer"]
    assert data["permissions"] == []
    assert data["email_verified"] is False


async def test_register_with_phone_only_normalizes_it(client):
    digits = unique_phone()[1:]
    pretty = f"+{digits[:3]} ({digits[3:5]}) {digits[5:8]}-{digits[8:10]}-{digits[10:]}"
    session, _ = await register(client, email=None, phone=pretty)
    me = (await client.get(f"{API}/me", headers=session.auth)).json()
    assert me["phone"] == f"+{digits}"
    assert me["email"] is None


async def test_register_duplicate_email_is_conflict(client):
    _, payload = await register(client)
    r = await client.post(
        f"{API}/auth/register",
        json={"email": str(payload["email"]).upper(), "password": PASSWORD},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "IDENTITY.EMAIL_TAKEN"


@pytest.mark.parametrize(
    "payload",
    [
        {"password": PASSWORD},  # neither email nor phone
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "a@example.com", "password": "short"},
        {"phone": "901234567", "password": PASSWORD},  # no country code
        {"email": "a@example.com", "password": PASSWORD, "status": "active"},  # mass assignment
        {"email": "a@example.com", "password": PASSWORD, "locale": "de"},
    ],
)
async def test_register_rejects_bad_input(client, payload):
    r = await client.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 422
    assert r.json()["code"] == "IDENTITY.VALIDATION_ERROR"


# ---------------------------------------------------------------- login


async def test_login_by_email_is_case_insensitive(client):
    _, payload = await register(client)
    r = await login(client, str(payload["email"]).upper())
    assert r.status_code == 200
    assert (await client.get(f"{API}/me", headers=login_from(r).auth)).status_code == 200


async def test_login_by_phone_accepts_formatting(client):
    phone = unique_phone()
    await register(client, phone=phone)
    r = await login(client, f"{phone[:4]} {phone[4:6]} {phone[6:]}")
    assert r.status_code == 200


async def test_wrong_password_and_unknown_user_look_the_same(client):
    _, payload = await register(client)
    wrong = await login(client, str(payload["email"]), "wrong-password")
    unknown = await login(client, unique_email())
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["code"] == unknown.json()["code"] == "IDENTITY.INVALID_CREDENTIALS"


async def test_account_locks_after_repeated_failures(client):
    _, payload = await register(client)
    email = str(payload["email"])
    for _ in range(5):
        assert (await login(client, email, "wrong-password")).status_code == 401
    r = await login(client, email)  # correct password, but locked
    assert r.status_code == 429
    assert r.json()["code"] == "IDENTITY.TOO_MANY_ATTEMPTS"


# ---------------------------------------------------------------- access token


async def test_me_requires_a_valid_token(client):
    assert (await client.get(f"{API}/me")).status_code == 401
    r = await client.get(f"{API}/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401
    assert r.json()["code"] == "IDENTITY.UNAUTHENTICATED"


# ---------------------------------------------------------------- refresh rotation


async def test_refresh_rotates_the_token(client):
    first, _ = await register(client)
    r = await refresh(client, first)
    assert r.status_code == 200
    second = login_from(r)
    assert second.refresh != first.refresh
    assert (await client.get(f"{API}/me", headers=second.auth)).status_code == 200


async def test_reusing_an_old_refresh_token_revokes_the_session(client):
    first, _ = await register(client)
    second = login_from(await refresh(client, first))

    replay = await refresh(client, first)  # a thief replays the copied old token
    assert replay.status_code == 401
    assert replay.json()["code"] == "IDENTITY.REFRESH_TOKEN_REUSED"

    # The legitimate user's newer tokens die with the session, immediately.
    assert (await client.get(f"{API}/me", headers=second.auth)).status_code == 401
    assert (await refresh(client, second)).status_code == 401


@pytest.mark.parametrize("csrf_header", [None, "wrong-value"])
async def test_refresh_requires_csrf_header(client, csrf_header):
    session, _ = await register(client)
    r = await with_cookies(client, "/auth/refresh", session.refresh, session.csrf, csrf_header)
    assert r.status_code == 403
    assert r.json()["code"] == "IDENTITY.CSRF_FAILED"


async def test_refresh_with_unknown_token_is_rejected(client):
    r = await refresh(client, Login(access="", refresh="made-up", csrf="c"))
    assert r.status_code == 401
    assert r.json()["code"] == "IDENTITY.INVALID_REFRESH_TOKEN"


# ---------------------------------------------------------------- logout and sessions


async def test_logout_kills_the_access_token_at_once(client):
    session, _ = await register(client)
    r = await logout(client, session)
    assert r.status_code == 204
    assert any(
        c.startswith(f'{REFRESH_COOKIE}=""') or "Max-Age=0" in c
        for c in r.headers.get_list("set-cookie")
    )
    assert (await client.get(f"{API}/me", headers=session.auth)).status_code == 401
    assert (await refresh(client, session)).status_code == 401


async def test_logout_without_cookie_is_harmless(client):
    client.cookies.clear()
    assert (await client.post(f"{API}/auth/logout")).status_code == 204


async def test_sessions_list_and_revoke_another_device(client):
    phone, _ = await register(client)
    email = (await client.get(f"{API}/me", headers=phone.auth)).json()["email"]
    laptop = login_from(await login(client, email))

    sessions = (await client.get(f"{API}/me/sessions", headers=laptop.auth)).json()
    assert len(sessions) == 2
    current = [s for s in sessions if s["current"]]
    assert len(current) == 1
    other = next(s for s in sessions if not s["current"])

    r = await client.delete(f"{API}/me/sessions/{other['id']}", headers=laptop.auth)
    assert r.status_code == 204
    assert (await client.get(f"{API}/me", headers=phone.auth)).status_code == 401
    assert (await client.get(f"{API}/me", headers=laptop.auth)).status_code == 200

    again = await client.delete(f"{API}/me/sessions/{other['id']}", headers=laptop.auth)
    assert again.status_code == 404


async def test_cannot_revoke_someone_elses_session(client):
    alice, _ = await register(client)
    bob, _ = await register(client)
    bob_session = (await client.get(f"{API}/me/sessions", headers=bob.auth)).json()[0]["id"]
    r = await client.delete(f"{API}/me/sessions/{bob_session}", headers=alice.auth)
    assert r.status_code == 404
    assert (await client.get(f"{API}/me", headers=bob.auth)).status_code == 200


# ---------------------------------------------------------------- profile and password


async def test_update_profile_ignores_nothing_it_should_not(client):
    session, _ = await register(client)
    r = await client.patch(f"{API}/me", json={"locale": "en"}, headers=session.auth)
    assert r.status_code == 200
    assert r.json()["locale"] == "en"
    forbidden = await client.patch(f"{API}/me", json={"status": "blocked"}, headers=session.auth)
    assert forbidden.status_code == 422


async def test_change_password_signs_out_other_devices(client):
    first, payload = await register(client)
    email = str(payload["email"])
    second = login_from(await login(client, email))

    wrong = await client.post(
        f"{API}/me/password",
        json={"current_password": "nope", "new_password": "another-long-password"},
        headers=first.auth,
    )
    assert wrong.status_code == 400

    r = await client.post(
        f"{API}/me/password",
        json={"current_password": PASSWORD, "new_password": "another-long-password"},
        headers=first.auth,
    )
    assert r.status_code == 204
    assert (await client.get(f"{API}/me", headers=first.auth)).status_code == 200
    assert (await client.get(f"{API}/me", headers=second.auth)).status_code == 401
    assert (await login(client, email)).status_code == 401
    assert (await login(client, email, "another-long-password")).status_code == 200
