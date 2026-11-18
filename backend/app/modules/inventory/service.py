"""Business logic of the `inventory` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

A variant without an ``inventory`` row simply has 0 in stock; the row appears on the
first change. After every change the catalog is told whether the variant can be bought
(``catalog.set_variant_in_stock``), so the storefront filters by availability without
reading this module's tables.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.events import publish
from app.core.models import uuid7
from app.modules.catalog import service as catalog
from app.modules.catalog.service import VariantBrief
from app.modules.inventory import repository as repo
from app.modules.inventory.events import StockLow
from app.modules.inventory.models import Inventory, StockMovement, StockReservation
from app.modules.inventory.schemas import MovementOut, StockOut, StockUpdate
from app.modules.stores.service import StoreAccess

MODULE = "inventory"
DEFAULT_THRESHOLD = 5

logger = logging.getLogger("app.modules.inventory")


def _error(code: str, detail: str, status: int) -> AppError:
    return AppError(MODULE, code, detail, status=status)


def _out(v: VariantBrief, stock: Inventory | None) -> StockOut:
    on_hand = stock.on_hand if stock else 0
    reserved = stock.reserved if stock else 0
    threshold = stock.low_stock_threshold if stock else DEFAULT_THRESHOLD
    available = on_hand - reserved
    return StockOut(
        variant_id=v.variant_id,
        product_id=v.product_id,
        product_title=v.product_title,
        product_status=v.product_status,
        sku=v.sku,
        attributes=v.attributes,
        on_hand=on_hand,
        reserved=reserved,
        available=available,
        low_stock_threshold=threshold,
        low_stock=available <= threshold,
    )


async def list_stock(
    db: AsyncSession, access: StoreAccess, low_stock_only: bool = False
) -> list[StockOut]:
    stock = await repo.stock_of_store(db, access.store_id)
    rows = [
        _out(v, stock.get(v.variant_id)) for v in await catalog.store_variants(db, access.store_id)
    ]
    if low_stock_only:
        rows = [r for r in rows if r.low_stock]
        rows.sort(key=lambda r: r.available)
    return rows


async def _variant(db: AsyncSession, store_id: uuid.UUID, variant_id: uuid.UUID) -> VariantBrief:
    found = await catalog.store_variants(db, store_id, variant_id)
    if not found:
        raise _error("VARIANT_NOT_FOUND", "Variant not found", 404)
    return found[0]


async def set_stock(
    db: AsyncSession,
    store_id: uuid.UUID,
    variant_id: uuid.UUID,
    data: StockUpdate,
    *,
    actor_id: uuid.UUID | None,
    reason: str = "manual",
) -> Inventory:
    """Changes stock in one transaction (row lock), writes the movement. Caller commits."""
    stock = await repo.lock_stock(db, variant_id)
    if stock is None:
        stock = Inventory(
            variant_id=variant_id,
            store_id=store_id,
            on_hand=0,
            reserved=0,
            low_stock_threshold=DEFAULT_THRESHOLD,
            version=1,
        )
        db.add(stock)
    before = stock.on_hand
    if data.on_hand is not None:
        stock.on_hand = data.on_hand
    elif data.delta is not None:
        stock.on_hand = before + data.delta
    if stock.on_hand < stock.reserved:
        raise _error(
            "BELOW_RESERVED",
            f"Stock cannot go below {stock.reserved}: that much is held for orders",
            409,
        )
    if data.low_stock_threshold is not None:
        stock.low_stock_threshold = data.low_stock_threshold
    stock.version += 1
    if stock.on_hand != before:
        db.add(
            StockMovement(
                id=uuid7(),
                variant_id=variant_id,
                store_id=store_id,
                delta=stock.on_hand - before,
                on_hand_after=stock.on_hand,
                reason=reason,
                note=data.note,
                actor_id=actor_id,
            )
        )
    await catalog.set_variant_in_stock(db, variant_id, stock.on_hand - stock.reserved > 0)
    return stock


async def update_stock(
    db: AsyncSession, access: StoreAccess, variant_id: uuid.UUID, data: StockUpdate
) -> StockOut:
    variant = await _variant(db, access.store_id, variant_id)
    stock = await set_stock(db, access.store_id, variant_id, data, actor_id=access.user_id)
    await db.commit()
    logger.info(
        "stock changed",
        extra={"extra_fields": {"variant_id": str(variant_id), "on_hand": stock.on_hand}},
    )
    return _out(variant, stock)


async def list_movements(
    db: AsyncSession, access: StoreAccess, variant_id: uuid.UUID, limit: int
) -> list[MovementOut]:
    await _variant(db, access.store_id, variant_id)
    return [MovementOut.model_validate(m) for m in await repo.movements(db, variant_id, limit)]


# ---------------------------------------------------------------- reservations (for orders)


@dataclass(frozen=True)
class ReserveLine:
    variant_id: uuid.UUID
    store_id: uuid.UUID
    quantity: int


async def available(db: AsyncSession, variant_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Free stock (``on_hand - reserved``) per variant; missing rows count as 0."""
    rows = await repo.stock_by_variants(db, variant_ids)
    return {
        vid: (rows[vid].on_hand - rows[vid].reserved) if vid in rows else 0 for vid in variant_ids
    }


async def reserve(
    db: AsyncSession, order_id: uuid.UUID, lines: list[ReserveLine], ttl_minutes: int
) -> None:
    """Holds stock for an unpaid order, all lines or none (the caller rolls back on error).
    Raises ``INVENTORY.OUT_OF_STOCK`` naming the variants that ran out."""
    short: list[str] = []
    expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    for line in sorted(lines, key=lambda x: x.variant_id):  # fixed order: no deadlocks
        stock = await repo.try_reserve(db, line.variant_id, line.quantity)
        if stock is None:
            short.append(str(line.variant_id))
            continue
        db.add(
            StockReservation(
                id=uuid7(),
                variant_id=line.variant_id,
                store_id=line.store_id,
                order_id=order_id,
                quantity=line.quantity,
                expires_at=expires_at,
            )
        )
        await catalog.set_variant_in_stock(db, line.variant_id, stock.on_hand - stock.reserved > 0)
    if short:
        raise _error("OUT_OF_STOCK", f"Not enough stock for variants: {', '.join(short)}", 409)


async def commit_reservations(db: AsyncSession, order_id: uuid.UUID) -> None:
    """Payment succeeded: the held stock leaves the shelf (movement ``sale``)."""
    low: list[tuple[uuid.UUID, uuid.UUID, int, int]] = []
    for r in await repo.reservations_of(db, order_id):
        stock = await repo.lock_stock(db, r.variant_id)
        if stock is None:  # variant deleted meanwhile
            r.status = "committed"
            continue
        stock.reserved -= r.quantity
        stock.on_hand -= r.quantity
        stock.version += 1
        r.status = "committed"
        db.add(
            StockMovement(
                id=uuid7(),
                variant_id=r.variant_id,
                store_id=r.store_id,
                delta=-r.quantity,
                on_hand_after=stock.on_hand,
                reason="sale",
                note=f"order {order_id}",
                actor_id=None,
            )
        )
        free = stock.on_hand - stock.reserved
        await catalog.set_variant_in_stock(db, r.variant_id, free > 0)
        # Stock on the shelf just went down to the threshold: tell the store once.
        if stock.on_hand <= stock.low_stock_threshold < stock.on_hand + r.quantity:
            low.append((r.store_id, r.variant_id, free, stock.low_stock_threshold))
    if low:
        info = await catalog.variants_for_sale(db, [v for _, v, _, _ in low])
        for store_id, variant_id, free, threshold in low:
            v = info.get(variant_id)
            await publish(
                db,
                StockLow(
                    store_id,
                    variant_id,
                    v.sku if v else "",
                    v.product_title if v else "",
                    free,
                    threshold,
                ),
            )


async def release_reservations(db: AsyncSession, order_id: uuid.UUID) -> None:
    """Order not paid or cancelled before payment: the held stock is free again."""
    for r in await repo.reservations_of(db, order_id):
        stock = await repo.lock_stock(db, r.variant_id)
        r.status = "released"
        if stock is None:
            continue
        stock.reserved = max(0, stock.reserved - r.quantity)
        stock.version += 1
        await catalog.set_variant_in_stock(db, r.variant_id, stock.on_hand - stock.reserved > 0)


async def return_to_stock(
    db: AsyncSession, store_id: uuid.UUID, variant_id: uuid.UUID, quantity: int, note: str
) -> None:
    """A paid item came back (cancelled after payment, or returned): movement ``return``."""
    await set_stock(
        db,
        store_id,
        variant_id,
        StockUpdate(delta=quantity, note=note[:255]),
        actor_id=None,
        reason="return",
    )


async def expired_reservation_orders(db: AsyncSession, limit: int = 100) -> list[uuid.UUID]:
    """Orders whose stock hold ran out (the orders module cancels them)."""
    return await repo.expired_order_ids(db, datetime.now(UTC), limit)
