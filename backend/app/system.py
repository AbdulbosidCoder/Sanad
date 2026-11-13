"""System endpoints: health checks and a live map of modules."""

import asyncio
import logging
from typing import Any

from fastapi import Response
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.modules import module_router
from app.core.redis import get_redis
from app.modules import ALL_MODULES

logger = logging.getLogger("app.system")

router = module_router("system")

CHECK_TIMEOUT_S = 2.0


async def _check_db() -> None:
    async with get_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _check_redis() -> None:
    await get_redis().ping()


@router.get("/health/live")
async def live() -> dict[str, str]:
    """The process is up. Used by Docker to restart a hung container."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(response: Response) -> dict[str, Any]:
    """Dependencies are reachable. Each component is reported separately,
    so you can see at a glance whether the database or Redis is down."""
    components: dict[str, str] = {}
    for name, check in (("database", _check_db), ("redis", _check_redis)):
        try:
            await asyncio.wait_for(check(), CHECK_TIMEOUT_S)
            components[name] = "ok"
        except Exception as exc:
            logger.warning("readiness check failed for %s: %s", name, exc)
            components[name] = "down"
    healthy = all(v == "ok" for v in components.values())
    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "components": components}


@router.get("/api/v1/system/modules")
async def modules() -> dict[str, Any]:
    """What the backend is made of and how modules connect.
    Disabled in production."""
    if get_settings().is_prod:
        from fastapi import HTTPException

        raise HTTPException(status_code=404)
    return {
        "modules": [
            {
                "name": m.name,
                "summary": m.summary,
                "depends_on": list(m.depends_on),
                "emits": list(m.emits),
                "listens_to": list(m.listens_to),
                "tables": list(m.tables),
                "endpoints": len(m.router.routes),
            }
            for m in ALL_MODULES
        ]
    }
