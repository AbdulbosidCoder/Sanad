"""Application entry point: builds the FastAPI app from core pieces and modules."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.modules import ALL_MODULES, setup_all
from app.system import router as system_router

API_PREFIX = "/api/v1"

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    for module in ALL_MODULES:
        if module.on_startup is None:
            continue
        try:
            await module.on_startup()
        except Exception:
            logger.exception("startup hook of module %s failed", module.name)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url=None if settings.is_prod else f"{API_PREFIX}/docs",
        openapi_url=None if settings.is_prod else f"{API_PREFIX}/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
    app.add_middleware(
        SecurityHeadersMiddleware, hsts=settings.is_prod, max_body_bytes=settings.max_body_bytes
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(system_router)
    setup_all()
    for module in ALL_MODULES:
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()
