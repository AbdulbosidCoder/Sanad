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

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.models import uuid7
from app.modules.catalog import service as catalog
from app.modules.catalog.service import VariantBrief
from app.modules.inventory import repository as repo
from app.modules.inventory.models import Inventory, StockMovement
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
