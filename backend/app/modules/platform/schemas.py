"""Response bodies of the `platform` API (ops dashboard)."""

from typing import Literal

from pydantic import BaseModel


class Queue(BaseModel):
    name: Literal["translations", "emails"]
    counts: dict[str, int]  # status -> rows
    schedule: str  # how often the worker takes it


class OpsOut(BaseModel):
    queues: list[Queue]
    database: bool
    redis: bool


class RetryOut(BaseModel):
    queue: str
    retried: int
