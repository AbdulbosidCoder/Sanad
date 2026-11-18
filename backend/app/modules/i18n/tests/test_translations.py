import pytest

from app.core.db import get_sessionmaker
from app.modules.i18n import service as i18n
from app.modules.i18n.translators import NoTranslator, use_translator
from tests.factories import API, category_and_brand, open_store, published_product, user_with_role

pytestmark = pytest.mark.usefixtures("database")


class Upper:
    """Deterministic test engine: '<locale>: TEXT'."""

    calls = 0

    async def translate(self, text: str, source: str, target: str, *, kind: str) -> str:
        Upper.calls += 1
        return f"{target}: {text.upper()}" if text else text


@pytest.fixture
def engine():
    use_translator(Upper())
    yield
    use_translator(None)


async def _work() -> None:
    async with get_sessionmaker()() as db:
        await i18n.process_pending(db, limit=10_000)


@pytest.fixture
async def setup_shop(client):
    admin, _ = await user_with_role(client, "admin")
    _, child, brand = await category_and_brand(client, admin)
    shop = await open_store(client, admin)
    product = await published_product(client, shop, child["id"], brand["id"])
    return shop, product


def _by_locale(rows):
    return {r["locale"]: r for r in rows}


async def test_new_product_is_queued_then_translated(client, engine, setup_shop):
    shop, product = setup_shop
    url = f"{API}/seller/products/{product['id']}/translations"
    rows = _by_locale((await client.get(url, headers=shop.headers)).json())
    assert rows["ru"]["state"] == "original"
    assert rows["uz"]["state"] == rows["en"]["state"] == "pending"

    await _work()
    rows = _by_locale((await client.get(url, headers=shop.headers)).json())
    assert rows["en"]["state"] == "machine"
    assert rows["en"]["title"] == f"en: {product['title'].upper()}"

    page = (await client.get(f"{API}/products/{product['slug']}?lang=en")).json()
    assert page["title"] == f"en: {product['title'].upper()}"
    page = (await client.get(f"{API}/products/{product['slug']}?lang=ru")).json()
    assert page["title"] == product["title"]  # original
    listing = (await client.get(f"{API}/products?q=&lang=uz")).json()
    assert any(p["title"].startswith("uz: ") for p in listing["items"])


async def test_manual_translation_is_kept_and_flagged_after_edit(client, engine, setup_shop):
    shop, product = setup_shop
    url = f"{API}/seller/products/{product['id']}/translations"
    await _work()
    r = await client.put(
        f"{url}/uz",
        json={"title": "Mening tarjimam", "description": "Tavsif"},
        headers=shop.headers,
    )
    assert r.status_code == 200, r.text
    assert _by_locale(r.json())["uz"]["state"] == "manual"

    r = await client.patch(
        f"{API}/seller/products/{product['id']}",
        json={"description": "Новое описание"},
        headers=shop.headers,
    )
    assert r.status_code == 200, r.text
    await _work()
    rows = _by_locale((await client.get(url, headers=shop.headers)).json())
    assert rows["uz"]["title"] == "Mening tarjimam"  # machine never overwrites the seller
    assert rows["uz"]["needs_review"] is True
    assert rows["en"]["description"] == "en: НОВОЕ ОПИСАНИЕ"

    r = await client.post(f"{url}/uz/retranslate", headers=shop.headers)
    assert _by_locale(r.json())["uz"]["state"] == "pending"
    await _work()
    rows = _by_locale((await client.get(url, headers=shop.headers)).json())
    assert rows["uz"]["state"] == "machine"


async def test_original_language_cannot_be_overwritten_and_others_cannot_edit(
    client, engine, setup_shop
):
    shop, product = setup_shop
    url = f"{API}/seller/products/{product['id']}/translations"
    r = await client.put(f"{url}/ru", json={"title": "Другое"}, headers=shop.headers)
    assert r.status_code == 409 and r.json()["code"] == "I18N.IS_ORIGINAL"

    admin, _ = await user_with_role(client, "admin")
    other = await open_store(client, admin)
    assert (await client.get(url, headers=other.headers)).status_code == 404


async def test_without_engine_jobs_fail_after_retries(client, setup_shop):
    shop, product = setup_shop
    use_translator(NoTranslator())
    try:
        for _ in range(i18n.MAX_ATTEMPTS):
            await _work()
    finally:
        use_translator(None)
    rows = _by_locale(
        (
            await client.get(
                f"{API}/seller/products/{product['id']}/translations", headers=shop.headers
            )
        ).json()
    )
    assert rows["en"]["state"] == "missing"
    page = (await client.get(f"{API}/products/{product['slug']}?lang=en")).json()
    assert page["title"] == product["title"]  # falls back to the original
