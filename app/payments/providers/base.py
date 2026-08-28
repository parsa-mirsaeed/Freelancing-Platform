from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ProviderTemporaryError(RuntimeError):
    """The provider outcome is unknown and the same idempotency key must be retried."""


@dataclass(frozen=True, slots=True)
class ProviderResult:
    reference: str
    status: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True)
class PaymentAction:
    kind: str
    redirect_url: str


@dataclass(frozen=True, slots=True)
class VerifiedWebhook:
    external_event_id: str
    event_type: str
    data: dict[str, object]


class PaymentProvider(Protocol):
    name: str
    webhook_signature_header: str

    def create_payment(
        self, *, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult: ...

    def verify_payment(self, *, reference: str) -> ProviderResult: ...

    def get_payment_action(self, *, reference: str) -> PaymentAction | None: ...

    def refund(
        self, *, reference: str, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult: ...

    def verify_refund(self, *, reference: str) -> ProviderResult: ...

    def validate_payout_destination(self, *, reference: str) -> str: ...

    def payout(
        self, *, user_reference: str, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult: ...

    def get_transaction(self, *, reference: str) -> ProviderResult: ...

    def verify_webhook(self, *, payload: bytes, signature: str) -> VerifiedWebhook: ...
