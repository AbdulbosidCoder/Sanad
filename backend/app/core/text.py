"""Slugs for URLs: ``"Nike Air Max 90"`` -> ``"nike-air-max-90"``. Cyrillic is transliterated."""

import re
import secrets

_CYRILLIC = dict(
    zip(
        "абвгдеёжзийклмнопрстуфхцчшщъыьэюяўқғҳ",
        [
            "a",
            "b",
            "v",
            "g",
            "d",
            "e",
            "yo",
            "zh",
            "z",
            "i",
            "y",
            "k",
            "l",
            "m",
            "n",
            "o",
            "p",
            "r",
            "s",
            "t",
            "u",
            "f",
            "kh",
            "ts",
            "ch",
            "sh",
            "shch",
            "",
            "y",
            "",
            "e",
            "yu",
            "ya",
            "o",
            "q",
            "g",
            "h",
        ],
        strict=True,
    )
)
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_length: int = 80) -> str:
    lowered = "".join(_CYRILLIC.get(ch, ch) for ch in text.lower().replace("'", ""))
    slug = _NON_SLUG.sub("-", lowered).strip("-")
    return slug[:max_length].strip("-") or "item"


def unique_slug(text: str) -> str:
    """Slug with a short random suffix, for things whose names repeat (products)."""
    return f"{slugify(text, 70)}-{secrets.token_hex(3)}"
