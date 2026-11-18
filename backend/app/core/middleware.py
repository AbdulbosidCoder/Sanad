"""Request id + access log middleware.

Also the last line of defence: an unexpected exception anywhere becomes a 500
problem+json that names the module and request id, and its traceback is logged.
"""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core import context
from app.core.errors import problem

logger = logging.getLogger("app.core.http")

REQUEST_ID_HEADER = "X-Request-Id"


def module_for_path(path: str) -> str:
    """Best guess before routing: ``/api/v1/orders/1`` -> ``orders``.
    The module router overwrites it with the real owner of the endpoint."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "api":
        return parts[2]
    return parts[0] if parts else "-"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex
        token = context.start(request_id, module_for_path(request.url.path))
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("unhandled error in module %s", context.current().module)
                response = problem(
                    500, "INTERNAL_ERROR", "Internal server error", context.current().module
                )
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "%s %s -> %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )
            return response
        finally:
            context.reset(token)


# Strict defaults for a JSON API. The docs page (dev only) needs scripts from a CDN.
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
_DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https:; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Security headers on every response, and a size limit for request bodies."""

    def __init__(self, app: object, *, hsts: bool, max_body_bytes: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.hsts = hsts
        self.max_body_bytes = max_body_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        length = request.headers.get("content-length")
        if length is not None and length.isdigit() and int(length) > self.max_body_bytes:
            response: Response = problem(
                413,
                "PAYLOAD_TOO_LARGE",
                "Request body is too large",
                "-",
            )
        else:
            response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        docs = request.url.path.endswith(("/docs", "/openapi.json"))
        h.setdefault("Content-Security-Policy", _DOCS_CSP if docs else _API_CSP)
        if self.hsts:
            h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        if request.url.path.startswith(("/api/v1/me", "/api/v1/auth", "/api/v1/admin")):
            h.setdefault("Cache-Control", "no-store")
        return response
