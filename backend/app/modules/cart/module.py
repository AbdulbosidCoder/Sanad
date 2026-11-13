"""Self-description of the `cart` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.cart.api import router

MODULE = ModuleInfo(
    name="cart",
    summary="Корзина (гостевая и пользователя), расчёт сумм.",
    router=router,
    depends_on=("catalog", "inventory"),
    emits=(),
    listens_to=(),
    tables=("carts", "cart_items"),
)
