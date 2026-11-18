"""Response language (docs/architecture/05-api-architecture.md, 5.1).

``?lang=`` wins, then the first supported language in ``Accept-Language``, then Uzbek.
"""

from typing import Literal

from fastapi import Header, Query

Locale = Literal["uz", "ru", "en"]
LOCALES: tuple[Locale, ...] = ("uz", "ru", "en")
DEFAULT_LOCALE: Locale = "uz"


def parse_accept_language(header: str | None) -> Locale | None:
    for part in (header or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LOCALES:
            return code
    return None


async def request_locale(
    lang: Locale | None = Query(None, description="uz | ru | en; overrides Accept-Language"),
    accept_language: str | None = Header(None),
) -> Locale:
    """FastAPI dependency: the language the client wants the answer in."""
    return lang or parse_accept_language(accept_language) or DEFAULT_LOCALE


def pick(names: dict[str, str], locale: str) -> str:
    """Text in ``locale``, else in the default language, else any non-empty one."""
    return names.get(locale) or names.get(DEFAULT_LOCALE) or next(iter(names.values()), "")
