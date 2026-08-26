from __future__ import annotations

import hashlib
import hmac
import json

from app.errors import ApiError
from app.payments.providers.base import PaymentAction, ProviderResult, VerifiedWebhook

_DEVELOPMENT_WEBHOOK_SECRET = "development-only-payment-webhook-secret"


class SandboxPaymentProvider:
    """Deterministic no-network adapter for local development and CI."""

    name = "sandbox"
    webhook_signature_header = "X-Payment-Signature"

    def __init__(self, *, webhook_secret: str = _DEVELOPMENT_WEBHOOK_SECRET) -> None:
        self._webhook_secret = webhook_secret

    def create_payment(
        self, *, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult:
        token = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
        return ProviderResult(
            reference=f"sandbox_pay_{amount_minor}_{currency}_{token}",
            status="PENDING",
            amount_minor=amount_minor,
            currency=currency,
        )

    def verify_payment(self, *, reference: str) -> ProviderResult:
        amount_minor, currency = self._parse_payment_reference(reference)
        return ProviderResult(reference, "CAPTURED", amount_minor, currency)

    def get_payment_action(self, *, reference: str) -> PaymentAction | None:
        self._parse_payment_reference(reference)
        return None

    def refund(
        self, *, reference: str, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult:
        self._parse_payment_reference(reference)
        token = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
        return ProviderResult(
            reference=f"sandbox_refund_{amount_minor}_{currency}_{token}",
            status="SUCCEEDED",
            amount_minor=amount_minor,
            currency=currency,
        )

    def verify_refund(self, *, reference: str) -> ProviderResult:
        amount_minor, currency = self._parse_refund_reference(reference)
        return ProviderResult(reference, "SUCCEEDED", amount_minor, currency)

    def validate_payout_destination(self, *, reference: str) -> str:
        if not reference:
            raise ApiError(
                "payout_destination_invalid",
                "Invalid payout destination",
                422,
                "Sandbox payout destination is required",
            )
        return reference

    def payout(
        self, *, user_reference: str, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult:
        token = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
        user_token = hashlib.sha256(user_reference.encode("utf-8")).hexdigest()[:8]
        return ProviderResult(
            reference=f"sandbox_payout_{user_token}_{amount_minor}_{currency}_{token}",
            status="SUCCEEDED",
            amount_minor=amount_minor,
            currency=currency,
        )

    def get_transaction(self, *, reference: str) -> ProviderResult:
        return self.verify_payment(reference=reference)

    def verify_webhook(self, *, payload: bytes, signature: str) -> VerifiedWebhook:
        expected = hmac.new(
            self._webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise ApiError(
                "invalid_webhook_signature",
                "Invalid webhook signature",
                401,
                "Payment webhook signature verification failed",
            )
        try:
            document = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ApiError(
                "invalid_webhook_payload",
                "Invalid webhook payload",
                400,
                "Payment webhook body must be valid JSON",
            ) from exc
        if not isinstance(document, dict):
            raise ApiError(
                "invalid_webhook_payload",
                "Invalid webhook payload",
                400,
                "Payment webhook body must be an object",
            )
        event_id = document.get("id")
        event_type = document.get("type")
        data = document.get("data", {})
        if not isinstance(event_id, str) or not event_id:
            raise ApiError(
                "invalid_webhook_payload", "Invalid webhook payload", 400, "id is required"
            )
        if not isinstance(event_type, str) or not event_type:
            raise ApiError(
                "invalid_webhook_payload", "Invalid webhook payload", 400, "type is required"
            )
        if not isinstance(data, dict):
            raise ApiError(
                "invalid_webhook_payload", "Invalid webhook payload", 400, "data must be an object"
            )
        normalized_data = dict(data)
        if "reference" in normalized_data and "provider_reference" not in normalized_data:
            normalized_data["provider_reference"] = normalized_data["reference"]
        return VerifiedWebhook(event_id, event_type, normalized_data)

    @staticmethod
    def _parse_payment_reference(reference: str) -> tuple[int, str]:
        parts = reference.split("_")
        if len(parts) != 5 or parts[:2] != ["sandbox", "pay"]:
            raise ApiError(
                "provider_reference_invalid",
                "Invalid provider reference",
                502,
                "Sandbox payment reference could not be verified",
            )
        try:
            amount_minor = int(parts[2])
        except ValueError as exc:
            raise ApiError(
                "provider_reference_invalid",
                "Invalid provider reference",
                502,
                "Sandbox payment reference contains an invalid amount",
            ) from exc
        return amount_minor, parts[3]

    @staticmethod
    def _parse_refund_reference(reference: str) -> tuple[int, str]:
        parts = reference.split("_")
        if len(parts) != 5 or parts[:2] != ["sandbox", "refund"]:
            raise ApiError(
                "provider_reference_invalid",
                "Invalid provider reference",
                502,
                "Sandbox refund reference could not be verified",
            )
        try:
            amount_minor = int(parts[2])
        except ValueError as exc:
            raise ApiError(
                "provider_reference_invalid",
                "Invalid provider reference",
                502,
                "Sandbox refund reference contains an invalid amount",
            ) from exc
        return amount_minor, parts[3]
