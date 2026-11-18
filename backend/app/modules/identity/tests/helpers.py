"""Test helpers: act like a browser that keeps the refresh and CSRF cookies itself.

Cookies are sent as an explicit header (the client's cookie jar is cleared first), so a
test can replay an *old* refresh token on purpose.
"""

import secrets
import uuid
from dataclasses import dataclass

from httpx import AsyncClient, Response

from app.modules.identity.api import CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE

API = "/api/v1"
PASSWORD = "correct-horse-battery"


def unique_email() -> str:
    return f"u{uuid.uuid4().hex[:16]}@example.com"


def unique_phone() -> str:
    return f"+99890{secrets.randbelow(10**7):07d}"


@dataclass
class Login:
    access: str
    refresh: str
    csrf: str

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access}"}


def login_from(response: Response) -> Login:
    assert response.status_code in (200, 201), response.text
    body = response.json()
    return Login(body["access_token"], response.cookies[REFRESH_COOKIE], body["csrf_token"])


async def register(client: AsyncClient, **fields: object) -> tuple[Login, dict[str, object]]:
    payload: dict[str, object] = {"email": unique_email(), "password": PASSWORD, **fields}
    r = await client.post(f"{API}/auth/register", json=payload)
    return login_from(r), payload


async def login(client: AsyncClient, login_name: str, password: str = PASSWORD) -> Response:
    return await client.post(f"{API}/auth/login", json={"login": login_name, "password": password})


async def with_cookies(
    client: AsyncClient, path: str, refresh: str, csrf: str | None, csrf_header: str | None
) -> Response:
    client.cookies.clear()
    cookie = f"{REFRESH_COOKIE}={refresh}" + (f"; {CSRF_COOKIE}={csrf}" if csrf else "")
    headers = {"Cookie": cookie}
    if csrf_header is not None:
        headers[CSRF_HEADER] = csrf_header
    return await client.post(f"{API}{path}", headers=headers)


async def refresh(client: AsyncClient, session: Login) -> Response:
    return await with_cookies(client, "/auth/refresh", session.refresh, session.csrf, session.csrf)


async def logout(client: AsyncClient, session: Login) -> Response:
    return await with_cookies(client, "/auth/logout", session.refresh, session.csrf, session.csrf)
