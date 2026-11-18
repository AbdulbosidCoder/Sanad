"""Request and response bodies of the `i18n` API."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

Locale = Literal["uz", "ru", "en"]


class TranslationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20000)] = ""


class TranslationOut(BaseModel):
    locale: Locale
    # original = the seller's own text; machine / manual = a translation; pending = queued;
    # missing = not translated (no engine configured or it keeps failing)
    state: Literal["original", "machine", "manual", "pending", "missing"]
    title: str | None
    description: str | None
    needs_review: bool = False
    updated_at: datetime | None = None
