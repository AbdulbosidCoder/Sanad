"""Per-request context (request id, module that handles it) shared by logs and errors.

The context object is created once per request by the middleware and *mutated*
by the module router, so the middleware, error handlers and logs all see the
same values even across task boundaries.
"""

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass
class RequestContext:
    request_id: str = "-"
    module: str = "-"


_EMPTY = RequestContext()
_ctx: ContextVar[RequestContext | None] = ContextVar("request_context", default=None)


def current() -> RequestContext:
    return _ctx.get() or _EMPTY


def start(request_id: str, module: str) -> Token[RequestContext | None]:
    return _ctx.set(RequestContext(request_id=request_id, module=module))


def reset(token: Token[RequestContext | None]) -> None:
    _ctx.reset(token)


def set_module(name: str) -> None:
    ctx = _ctx.get()
    if ctx is not None:
        ctx.module = name
