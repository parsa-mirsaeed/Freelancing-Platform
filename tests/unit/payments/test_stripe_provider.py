from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.errors import ApiError
from app.payments.providers.stripe import StripePaymentProvider

pytestmark = pytest.mark.unit


class FakeEndpoint:
    def __init__(self, *, create_result: Any = None, retrieve_result: Any = None) -> None:
        self.create_result = create_result
        self.retrieve_result = retrieve_result
        self.create_calls: list[tuple[dict[str, object], dict[str, object] | None]] = []
        self.retrieve_calls: list[str] = []

    def create(
        self,
        payload: dict[str, object],
        *,
        options: dict[str, object] | None = None,
    ) -> Any:
        self.create_calls.append((payload, options))
        return self.create_result

    def retrieve(self, reference: str) -> Any:
        self.retrieve_calls.append(reference)
        return self.retrieve_result


class FakeStripeClient:
    def __init__(
        self,
        *,
        checkout_sessions: FakeEndpoint | None = None,
        refunds: FakeEndpoint | None = None,
        accounts: FakeEndpoint | None = None,
        transfers: FakeEndpoint | None = None,
    ) -> None:
        self.v1 = SimpleNamespace(
            checkout=SimpleNamespace(sessions=checkout_sessions or FakeEndpoint()),
            refunds=refunds or FakeEndpoint(),
            accounts=accounts or FakeEndpoint(),
            transfers=transfers or FakeEndpoint(),
        )


def _provider(client: FakeStripeClient) -> StripePaymentProvider:
    return StripePaymentProvider(
        secret_key="sk_test_platform",
        webhook_secret="whsec_platform",
        checkout_success_url="https://app.example.test/payments/success?session={CHECKOUT_SESSION_ID}",
        checkout_cancel_url="https://app.example.test/payments/cancel",
        client=client,
    )


def test_checkout_creation_is_provider_idempotent_and_action_is_a_hosted_redirect() -> None:
    session = {
        "id": "cs_test_123",
        "status": "open",
        "payment_status": "unpaid",
        "amount_total": 1250,
        "currency": "usd",
        "url": "https://checkout.stripe.com/c/pay/cs_test_123",
    }
    checkout_sessions = FakeEndpoint(create_result=session, retrieve_result=session)
    provider = _provider(FakeStripeClient(checkout_sessions=checkout_sessions))

    result = provider.create_payment(
        amount_minor=1250,
        currency="USD",
        idempotency_key="fund-123",
    )
    assert result.reference == "cs_test_123"
    assert result.status == "PENDING"
    assert result.amount_minor == 1250
    assert result.currency == "USD"
    payload, options = checkout_sessions.create_calls[0]
    assert payload == {
        "mode": "payment",
        "success_url": "https://app.example.test/payments/success?session={CHECKOUT_SESSION_ID}",
        "cancel_url": "https://app.example.test/payments/cancel",
        "line_items": [
            {
                "quantity": 1,
                "price_data": {
                    "currency": "usd",
                    "unit_amount": 1250,
                    "product_data": {"name": "Milestone escrow funding"},
                },
            }
        ],
    }
    assert options == {"idempotency_key": "fund-123"}

    action = provider.get_payment_action(reference="cs_test_123")
    assert action is not None
    assert action.kind == "redirect"
    assert action.redirect_url == "https://checkout.stripe.com/c/pay/cs_test_123"


def test_paid_checkout_has_no_follow_up_action() -> None:
    session = {
        "id": "cs_test_paid",
        "status": "complete",
        "payment_status": "paid",
        "amount_total": 1250,
        "currency": "usd",
        "url": None,
    }
    provider = _provider(
        FakeStripeClient(checkout_sessions=FakeEndpoint(retrieve_result=session))
    )

    assert provider.get_payment_action(reference="cs_test_paid") is None


def test_expired_checkout_requires_a_new_funding_attempt() -> None:
    session = {
        "id": "cs_test_expired",
        "status": "expired",
        "payment_status": "unpaid",
        "amount_total": 1250,
        "currency": "usd",
        "url": None,
    }
    provider = _provider(
        FakeStripeClient(checkout_sessions=FakeEndpoint(retrieve_result=session))
    )

    with pytest.raises(ApiError, match="Payment action expired"):
        provider.get_payment_action(reference="cs_test_expired")


def test_stripe_webhook_maps_checkout_success_to_provider_neutral_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(FakeStripeClient())
    event = {
        "id": "evt_123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "status": "complete",
                "payment_status": "paid",
                "amount_total": 1250,
                "currency": "usd",
            }
        },
    }
    monkeypatch.setattr(
        "app.payments.providers.stripe.Webhook.construct_event",
        lambda *args, **kwargs: event,
    )

    verified = provider.verify_webhook(payload=b"{}", signature="t=1,v1=test")
    assert verified.external_event_id == "evt_123"
    assert verified.event_type == "payment.captured"
    assert verified.data == {
        "provider_reference": "cs_test_123",
        "amount_minor": 1250,
        "currency": "USD",
    }


def test_unpaid_checkout_completion_waits_for_async_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(FakeStripeClient())
    event = {
        "id": "evt_pending",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_pending",
                "payment_status": "unpaid",
                "amount_total": 1250,
                "currency": "usd",
            }
        },
    }
    monkeypatch.setattr(
        "app.payments.providers.stripe.Webhook.construct_event",
        lambda *args, **kwargs: event,
    )

    verified = provider.verify_webhook(payload=b"{}", signature="t=1,v1=test")
    assert verified.event_type == "payment.ignored"


def test_connected_account_is_verified_before_transfer() -> None:
    accounts = FakeEndpoint(retrieve_result={"id": "acct_ready", "payouts_enabled": True})
    transfers = FakeEndpoint(
        create_result={"id": "tr_123", "amount": 4000, "currency": "usd"}
    )
    provider = _provider(FakeStripeClient(accounts=accounts, transfers=transfers))

    assert provider.validate_payout_destination(reference="acct_ready") == "acct_ready"
    result = provider.payout(
        user_reference="acct_ready",
        amount_minor=4000,
        currency="USD",
        idempotency_key="payout-123",
    )
    assert result.reference == "tr_123"
    payload, options = transfers.create_calls[0]
    assert payload == {
        "amount": 4000,
        "currency": "usd",
        "destination": "acct_ready",
    }
    assert options == {"idempotency_key": "payout-123"}


def test_connected_account_must_be_payout_ready() -> None:
    accounts = FakeEndpoint(retrieve_result={"id": "acct_blocked", "payouts_enabled": False})
    provider = _provider(FakeStripeClient(accounts=accounts))

    with pytest.raises(ApiError, match="Payout destination not ready"):
        provider.validate_payout_destination(reference="acct_blocked")


def test_pending_refund_can_be_verified_without_creating_a_second_refund() -> None:
    checkout_sessions = FakeEndpoint(
        retrieve_result={
            "id": "cs_test_123",
            "payment_intent": "pi_123",
            "amount_total": 1250,
            "currency": "usd",
        }
    )
    refunds = FakeEndpoint(
        create_result={
            "id": "re_123",
            "status": "pending",
            "amount": 1250,
            "currency": "usd",
        },
        retrieve_result={
            "id": "re_123",
            "status": "succeeded",
            "amount": 1250,
            "currency": "usd",
        },
    )
    provider = _provider(
        FakeStripeClient(checkout_sessions=checkout_sessions, refunds=refunds)
    )

    created = provider.refund(
        reference="cs_test_123",
        amount_minor=1250,
        currency="USD",
        idempotency_key="refund-123",
    )
    assert created.status == "PENDING"
    refund_payload, options = refunds.create_calls[0]
    assert refund_payload == {"payment_intent": "pi_123", "amount": 1250}
    assert options == {"idempotency_key": "refund-123"}
    verified = provider.verify_refund(reference=created.reference)
    assert verified.status == "SUCCEEDED"
    assert len(refunds.create_calls) == 1
    assert refunds.retrieve_calls == ["re_123"]
