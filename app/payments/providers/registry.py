from __future__ import annotations

from app.errors import ApiError
from app.payments.providers.base import PaymentProvider
from app.payments.providers.sandbox import SandboxPaymentProvider


def get_provider(name: str) -> PaymentProvider:
    normalized = name.strip().lower()
    if normalized == "sandbox":
        return SandboxPaymentProvider()
    raise ApiError(
        "unsupported_payment_provider",
        "Unsupported payment provider",
        422,
        f"Payment provider {name!r} is not configured",
    )
