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
        payment_intents: FakeEndpoint | None = None,
        refunds: FakeEndpoint | None = None,
        accounts: FakeEndpoint | None = None,
        transfers: FakeEndpoint | None = None,
    ) -> None:
        self.v1 = SimpleNamespace(
            payment_intents=payment_intents or FakeEndpoint(),
            refunds=refunds or FakeEndpoint(),
            accounts=accounts or FakeEndpoint(),
            transfers=transfers or FakeEndpoint(),
        )


def _provider(client: FakeStripeClient) -> StripePaymentProvider:
    return StripePaymentProvider(
        secret_key="sk_test_platform",
        publishable_key="pk_test_platform",
        webhook_secret="whsec_platform",
        client=client,
    )


def test_payment_intent_creation_is_provider_idempotent_and_action_is_ephemeral() -> None:
    intent = {
        "id": "pi_123",
        "status": "requires_payment_method",
        "amount": 1250,
        "currency": "usd",
        "client_secret": "pi_123_secret_abc",
    }
    payment_intents = FakeEndpoint(create_result=intent, retrieve_result=intent)
    provider = _provider(FakeStripeClient(payment_intents=payment_intents))

    result = provider.create_payment(
        amount_minor=1250,
        currency="USD",
        idempotency_key="fund-123",
    )
    assert result.reference == "pi_123"
    assert result.amount_minor == 1250
    assert result.currency == "USD"
    payload, options = payment_intents.create_calls[0]
    assert payload == {
        "amount": 1250,
        "currency": "usd",
        "automatic_payment_methods": {"enabled": True},
    }
    assert options == {"idempotency_key": "fund-123"}

    action = provider.get_payment_action(reference="pi_123")
    assert action is not None
    assert action.kind == "stripe_payment_intent"
    assert action.client_secret == "pi_123_secret_abc"
    assert action.publishable_key == "pk_test_platform"


def test_stripe_webhook_maps_only_provider_neutral_payment_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = _provider(FakeStripeClient())
    event = {
        "id": "evt_123",
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_123",
                "amount": 1250,
                "amount_received": 1250,
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
        "provider_reference": "pi_123",
        "amount_minor": 1250,
        "currency": "USD",
    }


def test_connected_account_is_verified_before_transfer() -> None:
    accounts = FakeEndpoint(
        retrieve_result={"id": "acct_ready", "payouts_enabled": True}
    )
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
    accounts = FakeEndpoint(
        retrieve_result={"id": "acct_blocked", "payouts_enabled": False}
    )
    provider = _provider(FakeStripeClient(accounts=accounts))

    with pytest.raises(ApiError, match="Payout destination not ready"):
        provider.validate_payout_destination(reference="acct_blocked")


def test_pending_refund_can_be_verified_without_creating_a_second_refund() -> None:
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
    provider = _provider(FakeStripeClient(refunds=refunds))

    created = provider.refund(
        reference="pi_123",
        amount_minor=1250,
        currency="USD",
        idempotency_key="refund-123",
    )
    assert created.status == "PENDING"
    verified = provider.verify_refund(reference=created.reference)
    assert verified.status == "SUCCEEDED"
    assert len(refunds.create_calls) == 1
    assert refunds.retrieve_calls == ["re_123"]
