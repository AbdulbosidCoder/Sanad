"""Unified error format (RFC 9457 problem+json).

Every error response tells you *which module* failed, a stable machine ``code``
and the ``request_id`` to look up in the logs.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import context

logger = logging.getLogger("app.core.errors")

PROBLEM_JSON = "application/problem+json"


class AppError(Exception):
    """Base class for expected business errors raised by modules.

    Example: ``raise AppError("orders", "OUT_OF_STOCK", "Not enough stock", status=409)``
    """

    def __init__(
        self,
        module: str,
        code: str,
        detail: str,
        status: int = 400,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.module = module
        self.code = code
        self.detail = detail
        self.status = status
        self.headers = headers or {}


def problem(
    status: int,
    code: str,
    title: str,
    module: str,
    detail: str | None = None,
    errors: list[dict[str, object]] | None = None,
) -> JSONResponse:
    body: dict[str, object] = {
        "type": "about:blank",
        "status": status,
        "title": title,
        "code": f"{module.upper()}.{code}" if module != "-" else code,
        "module": module,
        "request_id": context.current().request_id,
    }
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        logger.info("business error %s.%s: %s", exc.module, exc.code, exc.detail)
        response = problem(exc.status, exc.code, "Request failed", exc.module, exc.detail)
        response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return problem(
            422, "VALIDATION_ERROR", "Invalid request", context.current().module, errors=errors
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem(exc.status_code, "HTTP_ERROR", str(exc.detail), context.current().module)
