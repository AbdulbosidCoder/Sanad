"""Payment providers behind one interface (docs/architecture/05-api-architecture.md, 5.4).

Adding Uzcard, Humo or Visa = a new class here + an entry in ``registry()`` + settings.
Orders and checkout do not change.
"""

import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from app.core.config import get_settings

FinalStatus = Literal["succeeded", "failed"]


@dataclass(frozen=True)
class PaymentRequest:
    amount: Decimal
    currency: str
    description: str


@dataclass(frozen=True)
class ProviderPayment:
    provider_payment_id: str
    status: Literal["pending", "succeeded", "failed"]
    # Where to send the buyer to pay (real providers); None for the fake one.
    redirect_url: str | None = None


@dataclass(frozen=True)
class ProviderWebhook:
    event_id: str
    provider_payment_id: str
    status: FinalStatus
    payload: dict[str, object]


@dataclass(frozen=True)
class ProviderRefund:
    provider_refund_id: str
    status: Literal["completed", "failed"]


class InvalidWebhook(Exception):
    pass


class PaymentProvider(Protocol):
    code: str
    is_test: bool

    async def create_payment(self, request: PaymentRequest) -> ProviderPayment: ...

    async def refund(self, provider_payment_id: str, amount: Decimal) -> ProviderRefund: ...

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> ProviderWebhook: ...


class FakeProvider:
    """Test payments: nothing is charged. The buyer picks the outcome
    (``POST /payments/{id}/confirm``), or a test sends a signed webhook."""

    code = "fake"
    is_test = True
    SIGNATURE_HEADER = "x-fake-signature"

    async def create_payment(self, request: PaymentRequest) -> ProviderPayment:
        return ProviderPayment(f"fake_{secrets.token_hex(12)}", "pending")

    async def refund(self, provider_payment_id: str, amount: Decimal) -> ProviderRefund:
        return ProviderRefund(f"fake_refund_{secrets.token_hex(8)}", "completed")

    @staticmethod
    def sign(body: bytes) -> str:
        secret = get_settings().fake_payments_webhook_secret.encode()
        return hmac.new(secret, body, hashlib.sha256).hexdigest()

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> ProviderWebhook:
        given = headers.get(self.SIGNATURE_HEADER, "")
        if not given or not hmac.compare_digest(given, self.sign(body)):
            raise InvalidWebhook("bad signature")
        try:
            data = json.loads(body)
            status = data["status"]
            if status not in ("succeeded", "failed"):
                raise InvalidWebhook("bad status")
            return ProviderWebhook(
                str(data["event_id"]), str(data["provider_payment_id"]), status, data
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidWebhook("bad body") from exc


def registry() -> dict[str, PaymentProvider]:
    """Providers enabled by configuration. The fake one is off in production."""
    providers: dict[str, PaymentProvider] = {}
    if get_settings().fake_payments_enabled:
        providers["fake"] = FakeProvider()
    return providers
