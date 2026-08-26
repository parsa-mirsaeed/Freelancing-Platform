from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from stripe import (
    APIConnectionError,
    APIError as StripeAPIError,
    RateLimitError,
    SignatureVerificationError,
    StripeClient,
    StripeError,
    Webhook,
)

from app.errors import ApiError
from app.payments.providers.base import (
    PaymentAction,
    ProviderResult,
    ProviderTemporaryError,
    VerifiedWebhook,
)


class StripePaymentProvider:
    """Stripe adapter that keeps Stripe resource details behind the provider boundary."""

    name = "stripe"
    webhook_signature_header = "Stripe-Signature"

    def __init__(
        self,
        *,
        secret_key: str,
        publishable_key: str,
        webhook_secret: str,
        max_network_retries: int = 2,
        client: Any | None = None,
    ) -> None:
        if not secret_key:
            raise RuntimeError("STRIPE_SECRET_KEY is required for the Stripe provider")
        if not publishable_key:
            raise RuntimeError("STRIPE_PUBLISHABLE_KEY is required for the Stripe provider")
        if not webhook_secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET is required for the Stripe provider")
        self._secret_key = secret_key
        self._publishable_key = publishable_key
        self._webhook_secret = webhook_secret
        self._client = client or StripeClient(
            secret_key,
            max_network_retries=max_network_retries,
        )

    def create_payment(
        self, *, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult:
        intent = self._provider_call(
            "create payment",
            lambda: self._client.v1.payment_intents.create(
                {
                    "amount": amount_minor,
                    "currency": currency.lower(),
                    "automatic_payment_methods": {"enabled": True},
                },
                options={"idempotency_key": idempotency_key},
            ),
        )
        return self._payment_result(intent)

    def verify_payment(self, *, reference: str) -> ProviderResult:
        intent = self._provider_call(
            "verify payment",
            lambda: self._client.v1.payment_intents.retrieve(reference),
        )
        return self._payment_result(intent)

    def get_payment_action(self, *, reference: str) -> PaymentAction | None:
        intent = self._provider_call(
            "retrieve payment action",
            lambda: self._client.v1.payment_intents.retrieve(reference),
        )
        status = str(self._value(intent, "status", ""))
        if status == "succeeded":
            return None
        client_secret = self._value(intent, "client_secret")
        if not isinstance(client_secret, str) or not client_secret:
            raise ApiError(
                "payment_action_unavailable",
                "Payment action unavailable",
                409,
                "Stripe did not return a client confirmation secret for this payment",
            )
        return PaymentAction(
            kind="stripe_payment_intent",
            client_secret=client_secret,
            publishable_key=self._publishable_key,
        )

    def refund(
        self, *, reference: str, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult:
        refund = self._provider_call(
            "create refund",
            lambda: self._client.v1.refunds.create(
                {
                    "payment_intent": reference,
                    "amount": amount_minor,
                },
                options={"idempotency_key": idempotency_key},
            ),
        )
        return self._refund_result(refund, fallback_currency=currency)

    def verify_refund(self, *, reference: str) -> ProviderResult:
        refund = self._provider_call(
            "verify refund",
            lambda: self._client.v1.refunds.retrieve(reference),
        )
        return self._refund_result(refund)

    def payout(
        self, *, user_reference: str, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult:
        if not user_reference.startswith("acct_"):
            raise ApiError(
                "payout_destination_not_configured",
                "Payout destination not configured",
                409,
                "Stripe payouts require a verified connected-account destination",
            )
        transfer = self._provider_call(
            "create transfer",
            lambda: self._client.v1.transfers.create(
                {
                    "amount": amount_minor,
                    "currency": currency.lower(),
                    "destination": user_reference,
                },
                options={"idempotency_key": idempotency_key},
            ),
        )
        return ProviderResult(
            reference=self._required_string(transfer, "id"),
            status="SUCCEEDED",
            amount_minor=self._required_int(transfer, "amount"),
            currency=self._required_string(transfer, "currency").upper(),
        )

    def get_transaction(self, *, reference: str) -> ProviderResult:
        return self.verify_payment(reference=reference)

    def verify_webhook(self, *, payload: bytes, signature: str) -> VerifiedWebhook:
        if not signature:
            raise ApiError(
                "invalid_webhook_signature",
                "Invalid webhook signature",
                401,
                "Stripe-Signature header is required",
            )
        try:
            event = Webhook.construct_event(
                payload,
                signature,
                self._webhook_secret,
                api_key=self._secret_key,
            )
        except SignatureVerificationError as exc:
            raise ApiError(
                "invalid_webhook_signature",
                "Invalid webhook signature",
                401,
                "Stripe webhook signature verification failed",
            ) from exc
        except ValueError as exc:
            raise ApiError(
                "invalid_webhook_payload",
                "Invalid webhook payload",
                400,
                "Stripe webhook body could not be parsed",
            ) from exc

        event_id = str(self._value(event, "id", ""))
        stripe_event_type = str(self._value(event, "type", ""))
        data = self._value(event, "data")
        obj = self._value(data, "object")
        if not event_id or not stripe_event_type:
            raise ApiError(
                "invalid_webhook_payload",
                "Invalid webhook payload",
                400,
                "Stripe webhook event id and type are required",
            )

        if stripe_event_type == "payment_intent.succeeded":
            reference = self._required_string(obj, "id")
            amount = self._value(obj, "amount_received")
            if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
                amount = self._required_int(obj, "amount")
            return VerifiedWebhook(
                external_event_id=event_id,
                event_type="payment.captured",
                data={
                    "provider_reference": reference,
                    "amount_minor": amount,
                    "currency": self._required_string(obj, "currency").upper(),
                },
            )
        if stripe_event_type == "payment_intent.payment_failed":
            return VerifiedWebhook(
                external_event_id=event_id,
                event_type="payment.failed",
                data={"provider_reference": self._required_string(obj, "id")},
            )
        return VerifiedWebhook(
            external_event_id=event_id,
            event_type="payment.ignored",
            data={"stripe_event_type": stripe_event_type},
        )

    def _payment_result(self, intent: Any) -> ProviderResult:
        return ProviderResult(
            reference=self._required_string(intent, "id"),
            status=self._payment_status(str(self._value(intent, "status", ""))),
            amount_minor=self._required_int(intent, "amount"),
            currency=self._required_string(intent, "currency").upper(),
        )

    def _refund_result(
        self, refund: Any, *, fallback_currency: str | None = None
    ) -> ProviderResult:
        currency = self._value(refund, "currency", fallback_currency)
        if not isinstance(currency, str) or not currency:
            raise ApiError(
                "provider_response_invalid",
                "Invalid provider response",
                502,
                "Stripe refund response is missing currency",
            )
        return ProviderResult(
            reference=self._required_string(refund, "id"),
            status=self._refund_status(str(self._value(refund, "status", "pending"))),
            amount_minor=self._required_int(refund, "amount"),
            currency=currency.upper(),
        )

    @staticmethod
    def _payment_status(status: str) -> str:
        if status == "succeeded":
            return "CAPTURED"
        if status == "canceled":
            return "CANCELLED"
        if status in {"requires_payment_method", "payment_failed"}:
            return "FAILED"
        return "PENDING"

    @staticmethod
    def _refund_status(status: str) -> str:
        if status == "succeeded":
            return "SUCCEEDED"
        if status in {"failed", "canceled"}:
            return "FAILED"
        return "PENDING"

    @staticmethod
    def _value(obj: Any, key: str, default: object | None = None) -> Any:
        if isinstance(obj, Mapping):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @classmethod
    def _required_string(cls, obj: Any, key: str) -> str:
        value = cls._value(obj, key)
        if not isinstance(value, str) or not value:
            raise ApiError(
                "provider_response_invalid",
                "Invalid provider response",
                502,
                f"Stripe response is missing {key}",
            )
        return value

    @classmethod
    def _required_int(cls, obj: Any, key: str) -> int:
        value = cls._value(obj, key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ApiError(
                "provider_response_invalid",
                "Invalid provider response",
                502,
                f"Stripe response has an invalid {key}",
            )
        return value

    @staticmethod
    def _provider_call(operation: str, request: Callable[[], Any]) -> Any:
        try:
            return request()
        except (APIConnectionError, StripeAPIError, RateLimitError) as exc:
            raise ProviderTemporaryError(f"Stripe could not {operation}; retry is safe") from exc
        except StripeError as exc:
            raise ApiError(
                "payment_provider_error",
                "Payment provider error",
                502,
                f"Stripe could not {operation}",
            ) from exc
