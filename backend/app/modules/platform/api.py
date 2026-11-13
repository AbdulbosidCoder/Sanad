"""HTTP endpoints of the `platform` module. Business logic lives in service.py."""

from app.core.modules import module_router

router = module_router("platform")
