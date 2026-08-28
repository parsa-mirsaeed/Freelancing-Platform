from __future__ import annotations

from flask import current_app

from app.errors import ApiError
from app.payments.providers.base import PaymentProvider
from app.payments.providers.sandbox import SandboxPaymentProvider
from app.payments.providers.stripe import StripePaymentProvider


def get_provider(name: str) -> PaymentProvider:
    if not bool(current_app.config["PAYMENT_RUNTIME_ENABLED"]):
        raise ApiError(
            "payment_runtime_disabled",
            "Payment runtime disabled",
            503,
            "External payment-provider operations are disabled for this workload",
        )

    normalized = name.strip().lower()
    if normalized == "sandbox":
        return SandboxPaymentProvider(
            webhook_secret=str(current_app.config["PAYMENT_WEBHOOK_SECRET"]),
        )
    if normalized == "stripe":
        return StripePaymentProvider(
            secret_key=str(current_app.config["STRIPE_SECRET_KEY"]),
            webhook_secret=str(current_app.config["STRIPE_WEBHOOK_SECRET"]),
            checkout_success_url=str(current_app.config["STRIPE_CHECKOUT_SUCCESS_URL"]),
            checkout_cancel_url=str(current_app.config["STRIPE_CHECKOUT_CANCEL_URL"]),
            max_network_retries=int(current_app.config["STRIPE_MAX_NETWORK_RETRIES"]),
        )
    raise ApiError(
        "unsupported_payment_provider",
        "Unsupported payment provider",
        422,
        f"Payment provider {name!r} is not configured",
    )
