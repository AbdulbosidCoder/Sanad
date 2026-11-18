"""Shared test fixtures for ``tests/`` and the module tests in ``app/modules/*/tests``.

Database tests run against a separate ``<name>_test`` database (derived from DATABASE_URL),
created and migrated automatically, so the dev database is never touched. In CI the URL
already ends with ``_test``. If PostgreSQL is not reachable, database tests are skipped.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.engine import URL, make_url

from app.core.config import Settings


def _point_to_test_database() -> None:
    # Must run before anything calls get_settings(): the settings object is cached.
    url = make_url(Settings().database_url)
    if not (url.database or "").endswith("_test"):
        url = url.set(database=f"{url.database}_test")
    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["APP_ENV"] = "test"


_point_to_test_database()

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import create_app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent


@pytest.fixture
def app():  # type: ignore[no-untyped-def]
    return create_app()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create_database(url: URL) -> None:
    import asyncpg

    conn = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="postgres",
        timeout=5,
    )
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", url.database):
            await conn.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await conn.close()


async def _sync_rbac(url: URL) -> None:
    # A private engine: the app's cached engine must be created on the test event loop.
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.modules.identity.service import sync_rbac

    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine)() as db:
            await sync_rbac(db)
            await db.commit()
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def database() -> None:
    """Creates (if needed) and migrates the test database, then writes the RBAC catalog."""
    from alembic import command
    from alembic.config import Config

    url = make_url(os.environ["DATABASE_URL"])
    try:
        asyncio.run(_create_database(url))
    except (OSError, TimeoutError) as exc:
        pytest.skip(f"PostgreSQL is not reachable: {exc}")

    config = Config()  # no ini file: keeps alembic from reconfiguring the app's logging
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(config, "head")
    asyncio.run(_sync_rbac(url))
