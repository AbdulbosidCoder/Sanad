"""Module registry: every business module describes itself here.

The registry powers ``GET /api/v1/system/modules`` (a live map of the system)
and lets ``main.py`` mount all routers without knowing module internals.
"""

from dataclasses import dataclass, field

from fastapi import APIRouter


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    summary: str
    router: APIRouter
    depends_on: tuple[str, ...] = ()
    emits: tuple[str, ...] = ()
    listens_to: tuple[str, ...] = ()
    tables: tuple[str, ...] = field(default=())


def module_router(name: str) -> APIRouter:
    """Router for a module: tags docs with the module name and marks the request
    context, so logs and error responses say which module handled the request."""
    from fastapi import Depends

    from app.core.context import set_module

    async def _mark_module() -> None:
        set_module(name)

    return APIRouter(tags=[name], dependencies=[Depends(_mark_module)])
