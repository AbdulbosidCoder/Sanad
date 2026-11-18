"""Rate limits: a fixed window counter per (rule, client).

Used as a FastAPI dependency: ``Depends(rate_limit("auth.login", 10, 60))``. The client is
the signed-in user when there is one, otherwise the IP. Over the limit -> 429 with
``Retry-After``. Storage: Redis (shared by every API process; required in prod) or memory
(one process: dev). ``RATE_LIMIT_ENABLED=false`` switches limits off (tests do that).
"""

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends, Request, Response

from app.core.auth import Principal, get_optional_principal
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.redis import get_redis


@dataclass(frozen=True)
class Hit:
    count: int
    reset_in: int  # seconds until the window ends


class MemoryStore:
    def __init__(self) -> None:
        self.windows: dict[str, tuple[int, float]] = {}

    async def hit(self, key: str, window: int) -> Hit:
        now = time.monotonic()
        count, ends = self.windows.get(key, (0, now + window))
        if now >= ends:
            count, ends = 0, now + window
        count += 1
        self.windows[key] = (count, ends)
        if len(self.windows) > 100_000:  # forget finished windows
            self.windows = {k: v for k, v in self.windows.items() if v[1] > now}
        return Hit(count, max(1, int(ends - now)))


class RedisStore:
    async def hit(self, key: str, window: int) -> Hit:
        redis = get_redis()
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window, nx=True)
        pipe.ttl(key)
        count, _, ttl = await pipe.execute()
        return Hit(int(count), max(1, int(ttl)))


_memory = MemoryStore()


def _store() -> MemoryStore | RedisStore:
    return RedisStore() if get_settings().rate_limit_storage == "redis" else _memory


def reset_memory() -> None:
    """Tests: forget all counters."""
    _memory.windows.clear()


def client_ip(request: Request) -> str:
    # Behind the reverse proxy the real address is the first X-Forwarded-For entry; the proxy
    # (infra/compose) overwrites the header, so clients cannot spoof it.
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "-"


def rate_limit(
    rule: str, limit: int, window_seconds: int, *, per: str = "user_or_ip"
) -> Callable[..., Awaitable[None]]:
    """``per``: ``user_or_ip`` (default) or ``ip`` (sign-in, registration)."""

    async def dependency(
        request: Request,
        response: Response,
        principal: Principal | None = Depends(get_optional_principal),
    ) -> None:
        if not get_settings().rate_limit_enabled:
            return
        who = (
            f"u:{principal.user_id}"
            if principal is not None and per == "user_or_ip"
            else f"ip:{client_ip(request)}"
        )
        hit = await _store().hit(f"rl:{rule}:{who}", window_seconds)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - hit.count))
        if hit.count > limit:
            raise AppError(
                "platform",
                "RATE_LIMITED",
                f"Too many requests, try again in {hit.reset_in} s",
                status=429,
                headers={"Retry-After": str(hit.reset_in)},
            )

    return dependency
