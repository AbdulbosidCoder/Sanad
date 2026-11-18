"""Machine translation behind one interface (docs/architecture/05-api-architecture.md, 5.5).

``TRANSLATOR=claude`` + ``ANTHROPIC_API_KEY`` uses the Claude API. Without it the
translator is ``none``: jobs wait, and buyers see the original text until translated.
Another engine (Google, DeepL, a local model) = one more class here.
"""

import logging
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger("app.modules.i18n.translators")

LANGUAGE_NAMES = {"uz": "Uzbek (Latin script)", "ru": "Russian", "en": "English"}


class TranslationUnavailable(Exception):
    """No engine configured, or it failed: the job is retried later."""


class Translator(Protocol):
    async def translate(self, text: str, source: str, target: str, *, kind: str) -> str: ...


class NoTranslator:
    async def translate(self, text: str, source: str, target: str, *, kind: str) -> str:
        raise TranslationUnavailable("no translator configured (TRANSLATOR=none)")


class ClaudeTranslator:
    """Translates through the Claude Messages API with a strict, short instruction."""

    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def translate(self, text: str, source: str, target: str, *, kind: str) -> str:
        if not text.strip():
            return text
        system = (
            "You translate e-commerce product texts for a marketplace in Uzbekistan. "
            f"Translate the user's text from {LANGUAGE_NAMES[source]} to "
            f"{LANGUAGE_NAMES[target]}. Keep brand names, model names, sizes and numbers "
            "unchanged. Keep line breaks. Answer with the translation only, no comments."
        )
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": "user", "content": f"<{kind}>\n{text}\n</{kind}>"}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(self.URL, json=body, headers=headers)
            r.raise_for_status()
            parts = r.json()["content"]
            out = "".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise TranslationUnavailable(f"translation API error: {exc}") from exc
        for tag in (f"<{kind}>", f"</{kind}>"):
            out = out.replace(tag, "")
        return out.strip()


_override: Translator | None = None


def use_translator(translator: Translator | None) -> None:
    """Replaces the configured engine (tests, demo data). None = back to configuration."""
    global _override
    _override = translator


def get_translator() -> Translator:
    if _override is not None:
        return _override
    s = get_settings()
    if s.translator == "claude" and s.anthropic_api_key:
        return ClaudeTranslator(s.anthropic_api_key, s.translation_model)
    return NoTranslator()
