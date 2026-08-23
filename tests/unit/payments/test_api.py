from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select

from app.extensions import db
from app.identity.mfa import totp_code_for_secret
from app.ledger.models import JournalTransaction
from app.payments.models import MilestoneFunding, ProviderEvent
from app.payments.service import reconcile_provider
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit

_WEBHOOK_SECRET = b"development-only-payment-webhook-secret"


def _enable_mfa_for_session(client, user: dict[str, object]) -> None:  # type: ignore[no-untyped-def]
    enrolled = client.post(
        "/api/v1/auth/mfa/totp/enroll",
        headers=auth_header(user),
        json={"password": "correct horse battery staple"},
    )
    assert enrolled.status_code == 200
    secret = enrolled.get_json()["secret"]
    confirmed = client.post(
        "/api/v1/auth/mfa/totp/confirm",
        headers=auth_header(user),
        json={"code": totp_code_for_secret(secret)},
    )
    assert confirmed.status_code == 200


def _active_contract_with_milestone(client, *, suffix: str):  # type: ignore[no-untyped-def]
    employer = register_user(client, email=f"{suffix}-employer@example.com", role="employer")
    freelancer = register_user(client, email=f"{suffix}-freelancer@example.com", role="freelancer")
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Money project", "description": "Financial flow", "skills": []},
    ).get_json()
    proposal = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json={
            "amount_minor": 9000,
            "currency": "USD",
            "delivery_days": 9,
            "milestones": [{"title": "Delivery", "amount_minor": 9000, "delivery_days": 9}],
        },
    ).get_json()
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/submit", headers=auth_header(freelancer)
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/accept", headers=auth_header(employer)
        ).status_code
        == 200
    )
    contract = client.get(
        f"/api/v1/projects/{project['id']}/contract", headers=auth_header(employer)
    ).get_json()
    document_hash = contract["version"]["document_hash"]
    for key, user in (
        (f"{suffix}-employer-sign", employer),
        (f"{suffix}-freelancer-sign", freelancer),
    ):
        response = client.post(
            f"/api/v1/contracts/{contract['id']}/sign",
            headers={**auth_header(user), "Idempotency-Key": key},
            json={"document_hash": document_hash},
        )
        assert response.status_code == 200
        contract = response.get_json()
    assert contract["status"] == "ACTIVE"
    return employer, freelancer, project, contract["version"]["milestones"][0]["id"]


def _capture_funding(
    client,
    *,
    employer: dict[str, object],
    milestone_id: str,
    event_id: str,
    idempotency_key: str,
):  # type: ignore[no-untyped-def]
    created = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": idempotency_key},
        json={"provider": "sandbox"},
    )
    assert created.status_code == 202
    intent = created.get_json()
    payload = json.dumps(
        {
            "id": event_id,
            "type": "payment.captured",
            "data": {
                "reference": intent["provider_reference"],
                "amount_minor": intent["amount_minor"],
                "currency": intent["currency"],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(_WEBHOOK_SECRET, payload, hashlib.sha256).hexdigest()
    captured = client.post(
        "/api/v1/payments/webhooks/sandbox",
        data=payload,
        headers={"X-Payment-Signature": signature, "Content-Type": "application/json"},
    )
    assert captured.status_code == 200
    return intent, payload, signature


def test_funding_release_wallet_and_payout_are_ledger_backed_and_idempotent(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, freelancer, project, milestone_id = _active_contract_with_milestone(
        client, suffix="money-flow"
    )
    intent, payload, signature = _capture_funding(
        client,
        employer=employer,
        milestone_id=milestone_id,
        event_id="evt-money-flow-captured",
        idempotency_key="fund-money-flow",
    )
    duplicate = client.post(
        "/api/v1/payments/webhooks/sandbox",
        data=payload,
        headers={"X-Payment-Signature": signature, "Content-Type": "application/json"},
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["status"] == "duplicate"
    funding_retry = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": "fund-money-flow"},
        json={"provider": "sandbox"},
    )
    assert funding_retry.status_code == 202
    assert funding_retry.get_json() == intent
    assert (
        len(
            list(
                db.session.scalars(
                    select(MilestoneFunding).where(
                        MilestoneFunding.payment_intent_id == uuid.UUID(intent["payment_intent_id"])
                    )
                )
            )
        )
        == 1
    )

    financials = client.get(
        f"/api/v1/milestones/{milestone_id}/financials", headers=auth_header(freelancer)
    )
    assert financials.status_code == 200
    assert financials.get_json()["escrow_balance_minor"] == 9000
    assert financials.get_json()["milestone_status"] == "FUNDED"
    reconciliation = reconcile_provider("sandbox")
    assert reconciliation.status == "SUCCEEDED"
    assert reconciliation.checked_count >= 1
    assert reconciliation.discrepancy_count == 0

    assert (
        client.post(
            f"/api/v1/milestones/{milestone_id}/start", headers=auth_header(freelancer)
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/milestones/{milestone_id}/submit",
            headers=auth_header(freelancer),
            json={"note": "done"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/milestones/{milestone_id}/approve", headers=auth_header(employer)
        ).status_code
        == 200
    )

    release_headers = {**auth_header(employer), "Idempotency-Key": "release-money-flow"}
    released = client.post(f"/api/v1/milestones/{milestone_id}/release", headers=release_headers)
    assert released.status_code == 200
    assert released.get_json()["milestone_status"] == "RELEASED"
    assert released.get_json()["escrow_balance_minor"] == 0
    assert (
        client.post(
            f"/api/v1/milestones/{milestone_id}/release", headers=release_headers
        ).status_code
        == 200
    )

    wallet = client.get("/api/v1/wallet", headers=auth_header(freelancer))
    assert wallet.status_code == 200
    assert wallet.get_json()["balances"] == [{"currency": "USD", "available_minor": 8100}]

    _enable_mfa_for_session(client, freelancer)
    payout_headers = {**auth_header(freelancer), "Idempotency-Key": "payout-money-flow"}
    payout = client.post(
        "/api/v1/payouts",
        headers=payout_headers,
        json={"amount_minor": 4000, "currency": "USD", "provider": "sandbox"},
    )
    assert payout.status_code == 200
    assert payout.get_json()["status"] == "SUCCEEDED"
    repeated_payout = client.post(
        "/api/v1/payouts",
        headers=payout_headers,
        json={"amount_minor": 4000, "currency": "USD", "provider": "sandbox"},
    )
    assert repeated_payout.status_code == 200
    assert repeated_payout.get_json()["payout_id"] == payout.get_json()["payout_id"]
    wallet = client.get("/api/v1/wallet", headers=auth_header(freelancer))
    assert wallet.get_json()["balances"] == [{"currency": "USD", "available_minor": 4100}]

    assert (
        client.post(
            f"/api/v1/projects/{project['id']}/close", headers=auth_header(employer)
        ).status_code
        == 200
    )
    release_journals = list(
        db.session.scalars(
            select(JournalTransaction).where(JournalTransaction.operation == "MILESTONE_RELEASE")
        )
    )
    assert len(release_journals) == 1


def test_full_prework_refund_reverses_escrow_entitlement(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, _freelancer, _project, milestone_id = _active_contract_with_milestone(
        client, suffix="money-refund"
    )
    _capture_funding(
        client,
        employer=employer,
        milestone_id=milestone_id,
        event_id="evt-money-refund-captured",
        idempotency_key="fund-money-refund",
    )
    headers = {**auth_header(employer), "Idempotency-Key": "refund-money-flow"}
    refunded = client.post(
        f"/api/v1/milestones/{milestone_id}/refund",
        headers=headers,
        json={"provider": "sandbox"},
    )
    assert refunded.status_code == 200
    assert refunded.get_json()["status"] == "SUCCEEDED"
    financials = client.get(
        f"/api/v1/milestones/{milestone_id}/financials", headers=auth_header(employer)
    )
    assert financials.get_json()["escrow_balance_minor"] == 0
    assert financials.get_json()["milestone_status"] == "CREATED"
    repeated = client.post(
        f"/api/v1/milestones/{milestone_id}/refund",
        headers=headers,
        json={"provider": "sandbox"},
    )
    assert repeated.status_code == 200
    assert repeated.get_json()["refund_id"] == refunded.get_json()["refund_id"]


def test_webhook_signature_and_event_identity_are_enforced(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, _freelancer, _project, milestone_id = _active_contract_with_milestone(
        client, suffix="money-webhook"
    )
    created = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": "fund-webhook"},
        json={"provider": "sandbox"},
    )
    intent = created.get_json()
    payload = json.dumps(
        {
            "id": "evt-webhook",
            "type": "payment.captured",
            "data": {
                "reference": intent["provider_reference"],
                "amount_minor": 9000,
                "currency": "USD",
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    invalid = client.post(
        "/api/v1/payments/webhooks/sandbox",
        data=payload,
        headers={"X-Payment-Signature": "wrong", "Content-Type": "application/json"},
    )
    assert invalid.status_code == 401
    signature = hmac.new(_WEBHOOK_SECRET, payload, hashlib.sha256).hexdigest()
    assert (
        client.post(
            "/api/v1/payments/webhooks/sandbox",
            data=payload,
            headers={"X-Payment-Signature": signature, "Content-Type": "application/json"},
        ).status_code
        == 200
    )
    conflicting_payload = json.dumps(
        {"id": "evt-webhook", "type": "unknown.event", "data": {}},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    conflict_signature = hmac.new(_WEBHOOK_SECRET, conflicting_payload, hashlib.sha256).hexdigest()
    conflict = client.post(
        "/api/v1/payments/webhooks/sandbox",
        data=conflicting_payload,
        headers={"X-Payment-Signature": conflict_signature, "Content-Type": "application/json"},
    )
    assert conflict.status_code == 409
    assert len(list(db.session.scalars(select(ProviderEvent)))) == 1
