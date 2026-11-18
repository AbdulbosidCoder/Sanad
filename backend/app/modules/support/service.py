"""Business logic of the `support` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

Who sees what:
- a customer sees only their tickets and never internal notes;
- ``support.tickets_handle`` (agent) sees tickets assigned to them and unassigned ones;
- ``support.tickets_read`` / ``support.tickets_assign`` (lead, admin) see all tickets.
"""

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import AppError
from app.core.events import publish
from app.core.models import uuid7
from app.modules.audit import service as audit
from app.modules.identity import service as identity
from app.modules.orders import service as orders
from app.modules.support import repository as repo
from app.modules.support.events import TicketCreated, TicketReplied
from app.modules.support.models import SupportMessage, SupportTicket
from app.modules.support.schemas import (
    AssignIn,
    MessageIn,
    MessageOut,
    StaffMessageIn,
    StaffTicketDetail,
    StaffTicketOut,
    TicketDetail,
    TicketIn,
    TicketOut,
    TicketUpdate,
)

MODULE = "support"
SEE_ALL = ("support.tickets_read", "support.tickets_assign")


def _error(code: str, detail: str, status: int) -> AppError:
    return AppError(MODULE, code, detail, status=status)


def _not_found() -> AppError:
    return _error("TICKET_NOT_FOUND", "Ticket not found", 404)


def _now() -> datetime:
    return datetime.now(UTC)


async def _number(db: AsyncSession) -> str:
    while True:
        number = f"T-{secrets.randbelow(10**8):08d}"
        if not await repo.number_taken(db, number):
            return number


def _message(
    ticket: SupportTicket, author: uuid.UUID, body: str, staff: bool, internal: bool
) -> SupportMessage:
    return SupportMessage(
        id=uuid7(),
        ticket_id=ticket.id,
        author_id=author,
        from_staff=staff,
        internal=internal,
        body=body,
        created_at=_now(),
    )


# ---------------------------------------------------------------- customer


async def create_ticket(db: AsyncSession, principal: Principal, data: TicketIn) -> TicketDetail:
    order_number = None
    if data.order_id is not None:
        ref = await orders.order_ref(db, data.order_id)
        if ref is None or ref[0] != principal.user_id:
            raise _error("ORDER_NOT_FOUND", "Order not found", 404)
        order_number = ref[1]
    ticket = SupportTicket(
        id=uuid7(),
        number=await _number(db),
        user_id=principal.user_id,
        subject=data.subject,
        category=data.category,
        priority="high" if data.category in ("payment", "return") else "normal",
        order_id=data.order_id,
        order_number=order_number,
        last_activity_at=_now(),
    )
    db.add(ticket)
    await db.flush()
    db.add(_message(ticket, principal.user_id, data.message, staff=False, internal=False))
    await publish(db, TicketCreated(ticket.id, principal.user_id, ticket.number, ticket.category))
    await db.commit()
    return await _customer_detail(db, ticket)


async def _own(
    db: AsyncSession, principal: Principal, ticket_id: uuid.UUID, lock: bool = False
) -> SupportTicket:
    ticket = await repo.get(db, ticket_id, lock)
    if ticket is None or ticket.user_id != principal.user_id:
        raise _not_found()
    return ticket


async def _customer_detail(db: AsyncSession, ticket: SupportTicket) -> TicketDetail:
    msgs = await repo.messages(db, ticket.id, with_internal=False)
    return TicketDetail(
        **TicketOut.model_validate(ticket).model_dump(),
        messages=[MessageOut.model_validate(m) for m in msgs],
    )


async def my_tickets(
    db: AsyncSession, principal: Principal, offset: int, limit: int
) -> list[TicketOut]:
    return [
        TicketOut.model_validate(t)
        for t in await repo.of_user(db, principal.user_id, offset, limit)
    ]


async def my_ticket(db: AsyncSession, principal: Principal, ticket_id: uuid.UUID) -> TicketDetail:
    return await _customer_detail(db, await _own(db, principal, ticket_id))


async def customer_reply(
    db: AsyncSession, principal: Principal, ticket_id: uuid.UUID, data: MessageIn
) -> TicketDetail:
    ticket = await _own(db, principal, ticket_id, lock=True)
    if ticket.status == "closed":
        raise _error("CLOSED", "The ticket is closed: open a new one", 409)
    db.add(_message(ticket, principal.user_id, data.body, staff=False, internal=False))
    ticket.status = "open"  # back to support, also from "resolved"
    ticket.resolved_at = None
    ticket.last_activity_at = _now()
    await db.commit()
    return await _customer_detail(db, ticket)


async def customer_close(
    db: AsyncSession, principal: Principal, ticket_id: uuid.UUID
) -> TicketDetail:
    ticket = await _own(db, principal, ticket_id, lock=True)
    ticket.status = "closed"
    ticket.last_activity_at = _now()
    await db.commit()
    return await _customer_detail(db, ticket)


# ---------------------------------------------------------------- staff


def _sees_all(principal: Principal) -> bool:
    return any(principal.has(p) for p in SEE_ALL)


async def _staff_ticket(
    db: AsyncSession, principal: Principal, ticket_id: uuid.UUID, lock: bool = False
) -> SupportTicket:
    ticket = await repo.get(db, ticket_id, lock)
    if ticket is None:
        raise _not_found()
    if not _sees_all(principal) and ticket.assignee_id not in (None, principal.user_id):
        raise _not_found()  # someone else's ticket: an agent does not even see it exists
    return ticket


async def _staff_detail(db: AsyncSession, ticket: SupportTicket) -> StaffTicketDetail:
    msgs = await repo.messages(db, ticket.id, with_internal=True)
    brief = await identity.user_brief(db, ticket.user_id)
    return StaffTicketDetail(
        **StaffTicketOut.model_validate(ticket).model_dump(),
        messages=[MessageOut.model_validate(m) for m in msgs],
        customer_email=brief[0] if brief else None,
        customer_name=brief[1] if brief else "",
    )


async def staff_queue(
    db: AsyncSession,
    principal: Principal,
    *,
    status: str | None,
    mine: bool,
    unassigned: bool,
    offset: int,
    limit: int,
) -> list[StaffTicketOut]:
    rows: Sequence[SupportTicket] = await repo.queue(
        db,
        status=status,
        assignee_id=principal.user_id if mine else None,
        mine_or_free=None if _sees_all(principal) else principal.user_id,
        unassigned=unassigned,
        offset=offset,
        limit=limit,
    )
    return [StaffTicketOut.model_validate(t) for t in rows]


async def staff_ticket(
    db: AsyncSession, principal: Principal, ticket_id: uuid.UUID
) -> StaffTicketDetail:
    return await _staff_detail(db, await _staff_ticket(db, principal, ticket_id))


async def staff_reply(
    db: AsyncSession, principal: Principal, ticket_id: uuid.UUID, data: StaffMessageIn
) -> StaffTicketDetail:
    ticket = await _staff_ticket(db, principal, ticket_id, lock=True)
    if ticket.status == "closed":
        raise _error("CLOSED", "The ticket is closed", 409)
    db.add(_message(ticket, principal.user_id, data.body, staff=True, internal=data.internal))
    if ticket.assignee_id is None:
        ticket.assignee_id = principal.user_id  # whoever answers first takes it
    if not data.internal:
        ticket.status = "answered"
        ticket.last_activity_at = _now()
        await publish(db, TicketReplied(ticket.id, ticket.user_id, ticket.number, ticket.subject))
    await db.commit()
    return await _staff_detail(db, ticket)


async def staff_update(
    db: AsyncSession, principal: Principal, ticket_id: uuid.UUID, data: TicketUpdate
) -> StaffTicketDetail:
    ticket = await _staff_ticket(db, principal, ticket_id, lock=True)
    if data.priority is not None:
        ticket.priority = data.priority
    if data.status is not None:
        ticket.status = data.status
        ticket.resolved_at = _now() if data.status in ("resolved", "closed") else None
    await db.commit()
    return await _staff_detail(db, ticket)


async def assign(
    db: AsyncSession, principal: Principal, ticket_id: uuid.UUID, data: AssignIn
) -> StaffTicketDetail:
    ticket = await _staff_ticket(db, principal, ticket_id, lock=True)
    before = ticket.assignee_id
    ticket.assignee_id = data.assignee_id
    await audit.record(
        db,
        principal.user_id,
        "support.assign",
        "support_ticket",
        ticket.id,
        {"from": before, "to": data.assignee_id},
    )
    await db.commit()
    return await _staff_detail(db, ticket)
