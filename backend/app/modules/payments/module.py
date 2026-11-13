"""Self-description of the `payments` module (see app/core/modules.py)."""

from app.core.modules import ModuleInfo
from app.modules.payments.api import router

MODULE = ModuleInfo(
    name="payments",
    summary="Платежи через PaymentProvider (V1: FakeProvider), вебхуки, возвраты денег, ledger.",
    router=router,
    depends_on=("audit",),
    emits=("PaymentSucceeded", "PaymentFailed", "RefundCompleted"),
    listens_to=(),
    tables=("payments", "payment_attempts", "refunds", "webhook_events", "ledger_entries"),
)
