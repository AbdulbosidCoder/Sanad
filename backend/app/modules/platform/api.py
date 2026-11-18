"""HTTP endpoints of the `platform` module. Business logic lives in service.py."""

from typing import Literal

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, require_permission
from app.core.db import get_session
from app.core.modules import module_router
from app.modules.platform import service
from app.modules.platform.schemas import OpsOut, RetryOut

router = module_router("platform")


@router.get("/admin/ops")
async def ops(
    _: Principal = Depends(require_permission("ops.read")),
    db: AsyncSession = Depends(get_session),
) -> OpsOut:
    """Background queues by status, database and Redis reachability."""
    return await service.overview(db)


@router.post("/admin/ops/queues/{queue}/retry")
async def retry(
    queue: Literal["translations", "emails"],
    actor: Principal = Depends(require_permission("ops.jobs_retry")),
    db: AsyncSession = Depends(get_session),
) -> RetryOut:
    return await service.retry(db, actor, queue)
