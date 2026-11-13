"""Application entry point: builds the FastAPI app from core pieces and modules."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware
from app.modules import ALL_MODULES
from app.system import router as system_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url=None if settings.is_prod else f"{API_PREFIX}/docs",
        openapi_url=None if settings.is_prod else f"{API_PREFIX}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(system_router)
    for module in ALL_MODULES:
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()
