from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProviderResult:
    reference: str
    status: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True)
class VerifiedWebhook:
    external_event_id: str
    event_type: str
    data: dict[str, object]


class PaymentProvider(Protocol):
    name: str

    def create_payment(
        self, *, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult: ...

    def verify_payment(self, *, reference: str) -> ProviderResult: ...

    def refund(
        self, *, reference: str, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult: ...

    def payout(
        self, *, user_reference: str, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult: ...

    def get_transaction(self, *, reference: str) -> ProviderResult: ...

    def verify_webhook(self, *, payload: bytes, signature: str) -> VerifiedWebhook: ...
