from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from stripe import (
    APIConnectionError,
    RateLimitError,
    SignatureVerificationError,
    StripeClient,
    StripeError,
    Webhook,
)
from stripe import (
    APIError as StripeAPIError,
)

from app.errors import ApiError
from app.observability import observe_histogram
from app.payments.providers.base import (
    PaymentAction,
    ProviderResult,
    ProviderTemporaryError,
    VerifiedWebhook,
)


class StripePaymentProvider:
    """Hosted Stripe Checkout adapter behind the provider-neutral money boundary."""

    name = "stripe"
    webhook_signature_header = "Stripe-Signature"

    def __init__(
        self,
        *,
        secret_key: str,
        webhook_secret: str,
        checkout_success_url: str,
        checkout_cancel_url: str,
        max_network_retries: int = 2,
        client: Any | None = None,
    ) -> None:
        if not secret_key:
            raise RuntimeError("STRIPE_SECRET_KEY is required for the Stripe provider")
        if not webhook_secret:
            raise RuntimeError("STRIPE_WEBHOOK_SECRET is required for the Stripe provider")
        if not checkout_success_url:
            raise RuntimeError("STRIPE_CHECKOUT_SUCCESS_URL is required for the Stripe provider")
        if not checkout_cancel_url:
            raise RuntimeError("STRIPE_CHECKOUT_CANCEL_URL is required for the Stripe provider")
        self._secret_key = secret_key
        self._webhook_secret = webhook_secret
        self._checkout_success_url = checkout_success_url
        self._checkout_cancel_url = checkout_cancel_url
        self._client = client or StripeClient(
            secret_key,
            max_network_retries=max_network_retries,
        )

    def create_payment(
        self, *, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult:
        try:
            session = self._provider_call(
                "create checkout session",
                lambda: self._client.v1.checkout.sessions.create(
                    {
                        "mode": "payment",
                        "success_url": self._checkout_success_url,
                        "cancel_url": self._checkout_cancel_url,
                        "line_items": [
                            {
                                "quantity": 1,
                                "price_data": {
                                    "currency": currency.lower(),
                                    "unit_amount": amount_minor,
                                    "product_data": {"name": "Milestone escrow funding"},
                                },
                            }
                        ],
                    },
                    options={"idempotency_key": idempotency_key},
                ),
            )
        except ProviderTemporaryError as exc:
            raise ApiError(
                "payment_provider_temporarily_unavailable",
                "Payment provider temporarily unavailable",
                503,
                "Stripe Checkout outcome is unknown; retry with the same Idempotency-Key",
            ) from exc
        return self._checkout_result(session)

    def verify_payment(self, *, reference: str) -> ProviderResult:
        session = self._retrieve_checkout(reference, operation="verify checkout payment")
        return self._checkout_result(session)

    def get_payment_action(self, *, reference: str) -> PaymentAction | None:
        session = self._retrieve_checkout(reference, operation="retrieve checkout action")
        if str(self._value(session, "payment_status", "")) == "paid":
            return None
        if str(self._value(session, "status", "")) == "expired":
            raise ApiError(
                "payment_action_expired",
                "Payment action expired",
                409,
                "The Stripe Checkout session expired; start funding again with a new "
                "idempotency key",
            )
        redirect_url = self._value(session, "url")
        if not isinstance(redirect_url, str) or not redirect_url:
            raise ApiError(
                "payment_action_unavailable",
                "Payment action unavailable",
                409,
                "Stripe did not return an active Checkout URL for this payment",
            )
        return PaymentAction(kind="redirect", redirect_url=redirect_url)

    def refund(
        self, *, reference: str, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult:
        session = self._retrieve_checkout(reference, operation="retrieve checkout for refund")
        payment_intent_reference = self._resource_reference(
            self._value(session, "payment_intent"),
            field="payment_intent",
        )
        refund = self._provider_call(
            "create refund",
            lambda: self._client.v1.refunds.create(
                {
                    "payment_intent": payment_intent_reference,
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

    def validate_payout_destination(self, *, reference: str) -> str:
        if not reference.startswith("acct_"):
            raise ApiError(
                "payout_destination_invalid",
                "Invalid payout destination",
                422,
                "Stripe payout destination must be a connected account id",
            )
        account = self._provider_call(
            "verify connected account",
            lambda: self._client.v1.accounts.retrieve(reference),
        )
        account_id = self._required_string(account, "id")
        if account_id != reference:
            raise ApiError(
                "payout_destination_invalid",
                "Invalid payout destination",
                422,
                "Stripe returned a different connected account id",
            )
        if self._value(account, "payouts_enabled") is not True:
            raise ApiError(
                "payout_destination_not_ready",
                "Payout destination not ready",
                409,
                "Stripe connected account is not enabled for payouts",
            )
        return account_id

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
        session = self._value(data, "object")
        occurred_at = self._event_occurred_at(event)
        if not event_id or not stripe_event_type:
            raise ApiError(
                "invalid_webhook_payload",
                "Invalid webhook payload",
                400,
                "Stripe webhook event id and type are required",
            )
        if occurred_at is not None:
            metric_event_type = (
                stripe_event_type
                if stripe_event_type
                in {
                    "checkout.session.completed",
                    "checkout.session.async_payment_succeeded",
                    "checkout.session.async_payment_failed",
                    "checkout.session.expired",
                }
                else "other"
            )
            observe_histogram(
                "payment_webhook_lag_seconds",
                max(0.0, (datetime.now(UTC) - occurred_at).total_seconds()),
                provider=self.name,
                event_type=metric_event_type,
            )

        if stripe_event_type in {
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
        }:
            if (
                stripe_event_type == "checkout.session.completed"
                and str(self._value(session, "payment_status", "")) != "paid"
            ):
                return VerifiedWebhook(
                    external_event_id=event_id,
                    event_type="payment.ignored",
                    data={"stripe_event_type": stripe_event_type},
                    occurred_at=occurred_at,
                )
            return VerifiedWebhook(
                external_event_id=event_id,
                event_type="payment.captured",
                data=self._checkout_event_data(session),
                occurred_at=occurred_at,
            )
        if stripe_event_type in {
            "checkout.session.async_payment_failed",
            "checkout.session.expired",
        }:
            return VerifiedWebhook(
                external_event_id=event_id,
                event_type="payment.failed",
                data={"provider_reference": self._required_string(session, "id")},
                occurred_at=occurred_at,
            )
        return VerifiedWebhook(
            external_event_id=event_id,
            event_type="payment.ignored",
            data={"stripe_event_type": stripe_event_type},
            occurred_at=occurred_at,
        )

    @classmethod
    def _event_occurred_at(cls, event: Any) -> datetime | None:
        created = cls._value(event, "created")
        if isinstance(created, bool) or not isinstance(created, (int, float)):
            return None
        try:
            return datetime.fromtimestamp(float(created), tz=UTC)
        except (OSError, OverflowError, ValueError):
            return None

    def _retrieve_checkout(self, reference: str, *, operation: str) -> Any:
        return self._provider_call(
            operation,
            lambda: self._client.v1.checkout.sessions.retrieve(reference),
        )

    def _checkout_result(self, session: Any) -> ProviderResult:
        return ProviderResult(
            reference=self._required_string(session, "id"),
            status=self._checkout_status(session),
            amount_minor=self._required_int(session, "amount_total"),
            currency=self._required_string(session, "currency").upper(),
        )

    def _checkout_event_data(self, session: Any) -> dict[str, object]:
        amount_minor = self._required_int(session, "amount_total")
        if amount_minor <= 0:
            raise ApiError(
                "provider_response_invalid",
                "Invalid provider response",
                502,
                "Stripe Checkout amount must be positive",
            )
        return {
            "provider_reference": self._required_string(session, "id"),
            "amount_minor": amount_minor,
            "currency": self._required_string(session, "currency").upper(),
        }

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

    @classmethod
    def _checkout_status(cls, session: Any) -> str:
        if str(cls._value(session, "payment_status", "")) == "paid":
            return "CAPTURED"
        if str(cls._value(session, "status", "")) == "expired":
            return "CANCELLED"
        return "PENDING"

    @staticmethod
    def _refund_status(status: str) -> str:
        if status == "succeeded":
            return "SUCCEEDED"
        if status in {"failed", "canceled"}:
            return "FAILED"
        return "PENDING"

    @classmethod
    def _resource_reference(cls, value: Any, *, field: str) -> str:
        if isinstance(value, str) and value:
            return value
        if isinstance(value, Mapping):
            return cls._required_string(value, "id")
        candidate = getattr(value, "id", None)
        if isinstance(candidate, str) and candidate:
            return candidate
        raise ApiError(
            "provider_response_invalid",
            "Invalid provider response",
            502,
            f"Stripe Checkout response is missing {field}",
        )

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
        return int(value)

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
