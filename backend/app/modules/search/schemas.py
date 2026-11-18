"""Request and response bodies of the `search` API."""

from pydantic import BaseModel


class Suggestion(BaseModel):
    kind: str  # history | product | brand | category
    text: str
    slug: str | None = None  # product / brand / category slug to open directly


class SuggestOut(BaseModel):
    items: list[Suggestion]


class PopularQuery(BaseModel):
    query: str
    count: int


class HistoryItem(BaseModel):
    query: str
