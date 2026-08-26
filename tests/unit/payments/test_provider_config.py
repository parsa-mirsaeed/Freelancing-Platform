from __future__ import annotations

import base64

import pytest

from app.config import Settings

pytestmark = pytest.mark.unit


def _key(byte: bytes) -> str:
    return base64.urlsafe_b64encode(byte * 32).decode("ascii").rstrip("=")


def _production_identity_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "production-secret-with-sufficient-entropy")
    monkeypatch.setenv("PII_ENCRYPTION_KEYS", f"primary:{_key(b'e')}")
    monkeypatch.setenv("PII_LOOKUP_KEY", _key(b'l'))


def test_payment_disabled_production_workload_does_not_require_stripe_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_identity_config(monkeypatch)
    monkeypatch.setenv("PAYMENT_RUNTIME_ENABLED", "false")
    monkeypatch.setenv("PAYMENT_DEFAULT_PROVIDER", "stripe")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("STRIPE_CHECKOUT_SUCCESS_URL", raising=False)
    monkeypatch.delenv("STRIPE_CHECKOUT_CANCEL_URL", raising=False)

    settings = Settings.from_env()
    assert settings.payment_runtime_enabled is False
    assert settings.payment_default_provider == "stripe"


def test_payment_enabled_production_workload_requires_complete_stripe_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_identity_config(monkeypatch)
    monkeypatch.setenv("PAYMENT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("PAYMENT_DEFAULT_PROVIDER", "stripe")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("STRIPE_CHECKOUT_SUCCESS_URL", raising=False)
    monkeypatch.delenv("STRIPE_CHECKOUT_CANCEL_URL", raising=False)

    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        Settings.from_env()


def test_payment_enabled_production_workload_requires_https_checkout_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_identity_config(monkeypatch)
    monkeypatch.setenv("PAYMENT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("PAYMENT_DEFAULT_PROVIDER", "stripe")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_platform")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_platform")
    monkeypatch.setenv(
        "STRIPE_CHECKOUT_SUCCESS_URL",
        "http://app.example.test/payments/success?session={CHECKOUT_SESSION_ID}",
    )
    monkeypatch.setenv("STRIPE_CHECKOUT_CANCEL_URL", "https://app.example.test/payments/cancel")

    with pytest.raises(RuntimeError, match="STRIPE_CHECKOUT_SUCCESS_URL must use HTTPS"):
        Settings.from_env()


def test_payment_enabled_production_workload_accepts_hosted_checkout_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_identity_config(monkeypatch)
    monkeypatch.setenv("PAYMENT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("PAYMENT_DEFAULT_PROVIDER", "stripe")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_platform")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_platform")
    monkeypatch.setenv(
        "STRIPE_CHECKOUT_SUCCESS_URL",
        "https://app.example.test/payments/success?session={CHECKOUT_SESSION_ID}",
    )
    monkeypatch.setenv("STRIPE_CHECKOUT_CANCEL_URL", "https://app.example.test/payments/cancel")

    settings = Settings.from_env()
    assert settings.stripe_checkout_success_url.startswith("https://")
    assert settings.stripe_checkout_cancel_url.startswith("https://")


def test_payment_enabled_production_workload_rejects_sandbox_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _production_identity_config(monkeypatch)
    monkeypatch.setenv("PAYMENT_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("PAYMENT_DEFAULT_PROVIDER", "sandbox")

    with pytest.raises(RuntimeError, match="cannot be sandbox"):
        Settings.from_env()
