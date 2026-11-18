"""Self-description of the `stores` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.stores.api import router

MODULE = ModuleInfo(
    name="stores",
    summary="Магазины, заявки продавцов, сотрудники магазина.",
    router=router,
    depends_on=("identity", "audit"),
    emits=(
        "SellerApplicationSubmitted",
        "StoreApproved",
        "SellerApplicationRejected",
        "StoreSuspended",
    ),
    listens_to=(),
    tables=("stores", "store_memberships", "seller_applications"),
)
