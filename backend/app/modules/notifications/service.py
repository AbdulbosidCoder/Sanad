"""Business logic of the `notifications` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

Every notification is written by an event handler in the transaction of the event, in
the recipient's language. E-mails go to ``email_outbox`` and the worker
(``notifications.send_emails``, every minute) sends them.
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.errors import AppError
from app.core.events import subscribe
from app.core.models import uuid7
from app.core.pagination import Page, next_cursor
from app.modules.identity import service as identity
from app.modules.inventory.events import StockLow
from app.modules.notifications import repository as repo
from app.modules.notifications.models import EmailOutbox, Notification, NotificationPreference
from app.modules.notifications.schemas import (
    NotificationOut,
    PreferencesIn,
    PreferencesOut,
    UnreadOut,
)
from app.modules.notifications.senders import SendFailed, get_sender
from app.modules.notifications.templates import EMAIL_KINDS, STATUS_NAMES, TEMPLATES, render
from app.modules.orders.events import (
    OrderCancelled,
    OrderPaid,
    OrderPlaced,
    SellerOrderStatusChanged,
)
from app.modules.payments.events import RefundCompleted
from app.modules.stores import service as stores
from app.modules.stores.events import SellerApplicationRejected, StoreApproved, StoreSuspended

MODULE = "notifications"
MAX_EMAIL_ATTEMPTS = 5
logger = logging.getLogger("app.modules.notifications")


# ---------------------------------------------------------------- sending


async def notify(
    db: AsyncSession,
    user_id: uuid.UUID,
    kind: str,
    params: dict[str, Any],
    *,
    link: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Writes the in-app notification and queues an e-mail (no commit)."""
    who = await identity.contact(db, user_id)
    if who is None or not who.active:
        return
    prefs = await repo.preferences(db, user_id)
    if prefs is not None and kind in prefs.muted_kinds:
        return
    strings = {k: str(v) for k, v in params.items() if v is not None}
    if "status" in strings:
        strings["status"] = STATUS_NAMES.get(strings["status"], {}).get(
            who.locale, strings["status"]
        )
    text = render(kind, who.locale, strings)
    db.add(
        Notification(
            id=uuid7(),
            user_id=user_id,
            kind=kind,
            title=text.title,
            body=text.body,
            link=link,
            data={k: str(v) for k, v in (data or {}).items()},
        )
    )
    email_on = prefs.email_enabled if prefs is not None else True
    if kind in EMAIL_KINDS and email_on and who.email:
        url = f"{get_settings().public_web_url}{link}" if link else ""
        db.add(
            EmailOutbox(
                id=uuid7(),
                user_id=user_id,
                to_address=who.email,
                subject=text.title,
                body="\n\n".join(p for p in (text.body, url) if p),
            )
        )


async def _notify_store(
    db: AsyncSession,
    store_id: uuid.UUID,
    permission: str,
    kind: str,
    params: dict[str, Any],
    **kw: Any,
) -> None:
    for user_id in await stores.staff_with_permission(db, store_id, permission):
        await notify(db, user_id, kind, params, **kw)


# ---------------------------------------------------------------- event handlers


async def on_order_placed(db: AsyncSession, e: OrderPlaced) -> None:
    await notify(db, e.user_id, "order_placed", {"number": e.number}, link=f"/orders/{e.order_id}")


async def on_order_paid(db: AsyncSession, e: OrderPaid) -> None:
    await notify(db, e.user_id, "order_paid", {"number": e.number}, link=f"/orders/{e.order_id}")
    for store_id in e.store_ids:
        await _notify_store(
            db,
            store_id,
            "orders.seller_manage",
            "store_new_order",
            {"number": e.number},
            link="/seller/orders",
            data={"order_id": e.order_id, "store_id": store_id},
        )


async def on_order_cancelled(db: AsyncSession, e: OrderCancelled) -> None:
    await notify(
        db,
        e.user_id,
        "order_cancelled",
        {"number": e.number, "reason": e.reason},
        link=f"/orders/{e.order_id}",
    )


async def on_seller_order_status(db: AsyncSession, e: SellerOrderStatusChanged) -> None:
    if e.to_status not in STATUS_NAMES:
        return
    await notify(
        db,
        e.user_id,
        "order_status",
        {"number": e.number, "status": e.to_status},
        link=f"/orders/{e.order_id}",
        data={"seller_order_id": e.seller_order_id, "status": e.to_status},
    )


async def on_refund_completed(db: AsyncSession, e: RefundCompleted) -> None:
    if e.user_id is None:
        return
    amount = f"{e.amount.quantize(Decimal('1')):,}".replace(",", " ")
    await notify(
        db, e.user_id, "refund_completed", {"amount": amount}, link=f"/orders/{e.order_id}"
    )


async def on_stock_low(db: AsyncSession, e: StockLow) -> None:
    await _notify_store(
        db,
        e.store_id,
        "inventory.write",
        "stock_low",
        {"sku": e.sku, "title": e.title, "available": e.available},
        link="/seller/inventory?low_stock=true",
        data={"variant_id": e.variant_id},
    )


async def on_store_approved(db: AsyncSession, e: StoreApproved) -> None:
    await notify(db, e.owner_id, "store_approved", {"name": e.name}, link="/seller")


async def on_application_rejected(db: AsyncSession, e: SellerApplicationRejected) -> None:
    await notify(db, e.user_id, "application_rejected", {"name": e.store_name, "note": e.note})


async def on_store_suspended(db: AsyncSession, e: StoreSuspended) -> None:
    await _notify_store(
        db,
        e.store_id,
        "store.settings_manage",
        "store_suspended",
        {"name": e.name, "reason": e.reason},
    )


def setup() -> None:
    subscribe(OrderPlaced, on_order_placed)
    subscribe(OrderPaid, on_order_paid)
    subscribe(OrderCancelled, on_order_cancelled)
    subscribe(SellerOrderStatusChanged, on_seller_order_status)
    subscribe(RefundCompleted, on_refund_completed)
    subscribe(StockLow, on_stock_low)
    subscribe(StoreApproved, on_store_approved)
    subscribe(SellerApplicationRejected, on_application_rejected)
    subscribe(StoreSuspended, on_store_suspended)


# ---------------------------------------------------------------- e-mail worker


async def send_pending(db: AsyncSession, limit: int = 50) -> int:
    sender = get_sender()
    sent = 0
    for mail in await repo.pending_emails(db, limit):
        mail.attempts += 1
        try:
            await sender.send(mail.to_address, mail.subject, mail.body)
        except SendFailed as exc:
            mail.last_error = str(exc)[:500]
            if mail.attempts >= MAX_EMAIL_ATTEMPTS:
                mail.status = "failed"
            continue
        mail.status = "sent"
        mail.sent_at = datetime.now(UTC)
        sent += 1
    await db.commit()
    return sent


async def send_emails_job() -> int:
    async with get_sessionmaker()() as db:
        count = await send_pending(db)
    if count:
        logger.info("emails sent", extra={"extra_fields": {"count": count}})
    return count


# ---------------------------------------------------------------- inbox API


async def inbox(
    db: AsyncSession, principal: Principal, unread_only: bool, offset: int, limit: int
) -> Page[NotificationOut]:
    rows = await repo.inbox(db, principal.user_id, unread_only, offset, limit + 1)
    return Page(
        items=[NotificationOut.model_validate(n) for n in rows[:limit]],
        next_cursor=next_cursor(offset, limit, len(rows)),
    )


async def unread(db: AsyncSession, principal: Principal) -> UnreadOut:
    return UnreadOut(unread=await repo.unread_count(db, principal.user_id))


async def mark_read(
    db: AsyncSession, principal: Principal, notification_id: uuid.UUID | None
) -> UnreadOut:
    changed = await repo.mark_read(db, principal.user_id, datetime.now(UTC), notification_id)
    if notification_id is not None and not changed:
        # Already read is fine; someone else's or missing is 404.
        mine = [n.id for n in await repo.inbox(db, principal.user_id, False, 0, 10_000)]
        if notification_id not in mine:
            raise AppError(MODULE, "NOT_FOUND", "Notification not found", status=404)
    await db.commit()
    return await unread(db, principal)


def _prefs_out(p: NotificationPreference | None) -> PreferencesOut:
    return PreferencesOut(
        email_enabled=p.email_enabled if p else True,
        muted_kinds=list(p.muted_kinds) if p else [],
        kinds=sorted(TEMPLATES),
    )


async def get_preferences(db: AsyncSession, principal: Principal) -> PreferencesOut:
    return _prefs_out(await repo.preferences(db, principal.user_id))


async def update_preferences(
    db: AsyncSession, principal: Principal, data: PreferencesIn
) -> PreferencesOut:
    p = await repo.preferences(db, principal.user_id)
    if p is None:
        p = NotificationPreference(id=uuid7(), user_id=principal.user_id)
        db.add(p)
    if data.email_enabled is not None:
        p.email_enabled = data.email_enabled
    if data.muted_kinds is not None:
        unknown = set(data.muted_kinds) - TEMPLATES.keys()
        if unknown:
            raise AppError(MODULE, "UNKNOWN_KIND", f"Unknown kinds: {sorted(unknown)}", status=422)
        p.muted_kinds = sorted(set(data.muted_kinds))
    await db.commit()
    return _prefs_out(p)
