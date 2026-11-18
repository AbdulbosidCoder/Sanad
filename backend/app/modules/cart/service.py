"""Business logic of the `cart` module.

This is the module's public interface: other modules may import from here
(and from events.py), never from models, repositories or api.

Prices in the cart are always today's prices from the catalog; the order copies them at
checkout. Items that cannot be bought now stay in the cart with a ``problem`` so the
buyer sees what happened, and block checkout until fixed.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.models import uuid7
from app.core.security import hash_token
from app.modules.cart import repository as repo
from app.modules.cart.models import MAX_QUANTITY, Cart, CartItem
from app.modules.cart.schemas import CartGroupOut, CartItemOut, CartOut, StoreRef
from app.modules.catalog import service as catalog
from app.modules.catalog.service import VariantForSale
from app.modules.inventory import service as inventory
from app.modules.stores import service as stores

MODULE = "cart"
MIN_GUEST_TOKEN = 32


def _error(code: str, detail: str, status: int) -> AppError:
    return AppError(MODULE, code, detail, status=status)


@dataclass(frozen=True)
class CartOwner:
    """A signed-in user, or a guest with a client-kept token."""

    user_id: uuid.UUID | None
    guest_token: str | None

    @property
    def token_hash(self) -> str | None:
        return hash_token(self.guest_token) if self.guest_token else None


def owner(user_id: uuid.UUID | None, guest_token: str | None) -> CartOwner:
    if user_id is None and guest_token is not None and len(guest_token) < MIN_GUEST_TOKEN:
        raise _error("BAD_CART_TOKEN", f"X-Cart-Token must be {MIN_GUEST_TOKEN}+ characters", 400)
    return CartOwner(user_id, guest_token if user_id is None else None)


async def _cart(db: AsyncSession, who: CartOwner, create: bool) -> Cart | None:
    cart = await repo.find_cart(db, who.user_id, who.token_hash)
    if cart is None and create:
        if who.user_id is None and who.token_hash is None:
            raise _error("CART_TOKEN_REQUIRED", "Sign in or send X-Cart-Token", 400)
        cart = Cart(id=uuid7(), user_id=who.user_id, guest_token_hash=who.token_hash)
        db.add(cart)
        await db.flush()
    return cart


def _problem(info: VariantForSale | None, quantity: int, free: int) -> str | None:
    if info is None or not info.sellable:
        return "unavailable"
    if quantity > free:
        return "not_enough_stock"
    return None


async def _view(db: AsyncSession, items: list[CartItem]) -> CartOut:
    ids = [i.variant_id for i in items]
    infos = await catalog.variants_for_sale(db, ids)
    free = await inventory.available(db, ids)
    groups: dict[uuid.UUID, list[CartItemOut]] = defaultdict(list)
    for item in items:
        info = infos.get(item.variant_id)
        if info is None:
            continue  # the variant was deleted: cart_items row is gone via FK cascade
        groups[info.store_id].append(
            CartItemOut(
                variant_id=info.variant_id,
                product_id=info.product_id,
                product_slug=info.product_slug,
                title=info.product_title,
                sku=info.sku,
                attributes=info.attributes,
                cover_url=info.cover_url,
                unit_price=info.price,
                compare_at_price=info.compare_at_price,
                quantity=item.quantity,
                line_total=info.price * item.quantity,
                available=free.get(item.variant_id, 0),
                problem=_problem(info, item.quantity, free.get(item.variant_id, 0)),
            )
        )
    out: list[CartGroupOut] = []
    for store_id, lines in groups.items():
        brief = await stores.get_store_brief(db, store_id)
        ref = StoreRef(
            id=store_id, slug=brief.slug if brief else "", name=brief.name if brief else ""
        )
        out.append(
            CartGroupOut(
                store=ref, items=lines, subtotal=sum((x.line_total for x in lines), Decimal(0))
            )
        )
    all_lines = [x for g in out for x in g.items]
    return CartOut(
        groups=out,
        item_count=sum(x.quantity for x in all_lines),
        total=sum((g.subtotal for g in out), Decimal(0)),
        can_checkout=bool(all_lines) and all(x.problem is None for x in all_lines),
    )


async def get_cart(db: AsyncSession, who: CartOwner) -> CartOut:
    cart = await _cart(db, who, create=False)
    return await _view(db, list(await repo.items_of(db, cart.id)) if cart else [])


async def _check_can_buy(db: AsyncSession, variant_id: uuid.UUID, quantity: int) -> None:
    info = (await catalog.variants_for_sale(db, [variant_id])).get(variant_id)
    if info is None or not info.sellable:
        raise _error("UNAVAILABLE", "This item is not for sale", 404)
    free = (await inventory.available(db, [variant_id]))[variant_id]
    if quantity > free:
        raise _error("NOT_ENOUGH_STOCK", f"Only {free} left", 409)


async def add_item(
    db: AsyncSession, who: CartOwner, variant_id: uuid.UUID, quantity: int
) -> CartOut:
    cart = await _cart(db, who, create=True)
    assert cart is not None  # noqa: S101 - create=True never returns None
    item = await repo.get_item(db, cart.id, variant_id)
    total = min((item.quantity if item else 0) + quantity, MAX_QUANTITY)
    await _check_can_buy(db, variant_id, total)
    if item is None:
        db.add(CartItem(cart_id=cart.id, variant_id=variant_id, quantity=total))
    else:
        item.quantity = total
    await db.commit()
    return await get_cart(db, who)


async def set_quantity(
    db: AsyncSession, who: CartOwner, variant_id: uuid.UUID, quantity: int
) -> CartOut:
    cart = await _cart(db, who, create=False)
    item = await repo.get_item(db, cart.id, variant_id) if cart else None
    if item is None:
        raise _error("ITEM_NOT_FOUND", "Not in the cart", 404)
    if quantity > item.quantity:
        await _check_can_buy(db, variant_id, quantity)
    item.quantity = quantity
    await db.commit()
    return await get_cart(db, who)


async def remove_item(db: AsyncSession, who: CartOwner, variant_id: uuid.UUID) -> CartOut:
    cart = await _cart(db, who, create=False)
    item = await repo.get_item(db, cart.id, variant_id) if cart else None
    if item is not None:
        await db.delete(item)
        await db.commit()
    return await get_cart(db, who)


async def clear_cart(db: AsyncSession, who: CartOwner) -> None:
    cart = await _cart(db, who, create=False)
    if cart is not None:
        await repo.clear(db, cart.id)
        await db.commit()


async def merge(db: AsyncSession, user_id: uuid.UUID, guest_token: str) -> CartOut:
    """Moves a guest cart into the user's cart after sign-in (quantities add up)."""
    guest = await repo.find_cart(db, None, hash_token(guest_token))
    me = CartOwner(user_id, None)
    if guest is not None:
        cart = await _cart(db, me, create=True)
        assert cart is not None  # noqa: S101
        for g in await repo.items_of(db, guest.id):
            mine = await repo.get_item(db, cart.id, g.variant_id)
            if mine is None:
                db.add(CartItem(cart_id=cart.id, variant_id=g.variant_id, quantity=g.quantity))
            else:
                mine.quantity = min(mine.quantity + g.quantity, MAX_QUANTITY)
        await db.delete(guest)
        await db.commit()
    return await get_cart(db, me)


# ---------------------------------------------------------------- for the orders module


@dataclass(frozen=True)
class CheckoutLine:
    item: VariantForSale
    quantity: int


async def checkout_lines(db: AsyncSession, user_id: uuid.UUID) -> list[CheckoutLine]:
    """The user's cart, ready to become an order. Raises if anything cannot be bought."""
    cart = await _cart(db, CartOwner(user_id, None), create=False)
    items = list(await repo.items_of(db, cart.id)) if cart else []
    if not items:
        raise _error("CART_EMPTY", "The cart is empty", 409)
    view = await _view(db, items)
    if not view.can_checkout:
        raise _error("CART_HAS_PROBLEMS", "Some items are unavailable: check the cart", 409)
    infos = await catalog.variants_for_sale(db, [i.variant_id for i in items])
    return [CheckoutLine(infos[i.variant_id], i.quantity) for i in items]


async def clear_user_cart(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Empties the cart in the caller's transaction (no commit)."""
    cart = await _cart(db, CartOwner(user_id, None), create=False)
    if cart is not None:
        await repo.clear(db, cart.id)


async def restore(db: AsyncSession, user_id: uuid.UUID, lines: list[tuple[uuid.UUID, int]]) -> None:
    """Puts items back into the user's cart (an unpaid order was cancelled). No commit."""
    cart = await _cart(db, CartOwner(user_id, None), create=True)
    assert cart is not None  # noqa: S101
    for variant_id, quantity in lines:
        item = await repo.get_item(db, cart.id, variant_id)
        if item is None:
            db.add(
                CartItem(
                    cart_id=cart.id, variant_id=variant_id, quantity=min(quantity, MAX_QUANTITY)
                )
            )
        else:
            item.quantity = min(item.quantity + quantity, MAX_QUANTITY)
