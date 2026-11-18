"""HTTP endpoints of the `support` module. Business logic lives in service.py."""

import uuid

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_permission
from app.core.db import get_session
from app.core.modules import module_router
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT, decode_cursor
from app.modules.support import service
from app.modules.support.schemas import (
    AssignIn,
    MessageIn,
    StaffMessageIn,
    StaffTicketDetail,
    StaffTicketOut,
    Status,
    TicketDetail,
    TicketIn,
    TicketOut,
    TicketUpdate,
)

router = module_router("support")
Limit = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)
_agent = require_permission("support.tickets_handle")


def _offset(cursor: str | None) -> int:
    return decode_cursor(cursor, "support")


@router.post("/support/tickets", status_code=201)
async def create(
    data: TicketIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> TicketDetail:
    return await service.create_ticket(db, principal, data)


@router.get("/support/tickets")
async def mine(
    cursor: str | None = None,
    limit: int = Limit,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> list[TicketOut]:
    return await service.my_tickets(db, principal, _offset(cursor), limit)


@router.get("/support/tickets/{ticket_id}")
async def one(
    ticket_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> TicketDetail:
    return await service.my_ticket(db, principal, ticket_id)


@router.post("/support/tickets/{ticket_id}/messages")
async def reply(
    ticket_id: uuid.UUID,
    data: MessageIn,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> TicketDetail:
    return await service.customer_reply(db, principal, ticket_id, data)


@router.post("/support/tickets/{ticket_id}/close")
async def close(
    ticket_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_session),
) -> TicketDetail:
    return await service.customer_close(db, principal, ticket_id)


@router.get("/admin/support/tickets")
async def queue(
    status: Status | None = None,
    mine: bool = False,
    unassigned: bool = False,
    cursor: str | None = None,
    limit: int = Limit,
    principal: Principal = Depends(_agent),
    db: AsyncSession = Depends(get_session),
) -> list[StaffTicketOut]:
    """Longest waiting first. Agents see their own and unassigned tickets."""
    return await service.staff_queue(
        db,
        principal,
        status=status,
        mine=mine,
        unassigned=unassigned,
        offset=_offset(cursor),
        limit=limit,
    )


@router.get("/admin/support/tickets/{ticket_id}")
async def staff_one(
    ticket_id: uuid.UUID,
    principal: Principal = Depends(_agent),
    db: AsyncSession = Depends(get_session),
) -> StaffTicketDetail:
    return await service.staff_ticket(db, principal, ticket_id)


@router.post("/admin/support/tickets/{ticket_id}/messages")
async def staff_reply(
    ticket_id: uuid.UUID,
    data: StaffMessageIn,
    principal: Principal = Depends(_agent),
    db: AsyncSession = Depends(get_session),
) -> StaffTicketDetail:
    """An answer to the customer, or an internal note (``internal: true``)."""
    return await service.staff_reply(db, principal, ticket_id, data)


@router.patch("/admin/support/tickets/{ticket_id}")
async def staff_update(
    ticket_id: uuid.UUID,
    data: TicketUpdate,
    principal: Principal = Depends(_agent),
    db: AsyncSession = Depends(get_session),
) -> StaffTicketDetail:
    return await service.staff_update(db, principal, ticket_id, data)


@router.post("/admin/support/tickets/{ticket_id}/assign")
async def assign(
    ticket_id: uuid.UUID,
    data: AssignIn,
    principal: Principal = Depends(require_permission("support.tickets_assign")),
    db: AsyncSession = Depends(get_session),
) -> StaffTicketDetail:
    return await service.assign(db, principal, ticket_id, data)
