from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select

from app.contracts.models import Contract
from app.extensions import db
from app.ledger.models import JournalTransaction
from app.payments.models import MilestoneFunding, PaymentIntent
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit

_WEBHOOK_SECRET = b"development-only-payment-webhook-secret"


def _active_contract_with_pending_funding(client, *, suffix: str):  # type: ignore[no-untyped-def]
    employer = register_user(client, email=f"{suffix}-employer@example.com", role="employer")
    freelancer = register_user(client, email=f"{suffix}-freelancer@example.com", role="freelancer")
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Pending funding", "description": "Race boundary", "skills": []},
    ).get_json()
    proposal = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json={
            "amount_minor": 7000,
            "currency": "USD",
            "delivery_days": 4,
            "milestones": [{"title": "Delivery", "amount_minor": 7000, "delivery_days": 4}],
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
        signed = client.post(
            f"/api/v1/contracts/{contract['id']}/sign",
            headers={**auth_header(user), "Idempotency-Key": key},
            json={"document_hash": document_hash},
        )
        assert signed.status_code == 200
        contract = signed.get_json()
    milestone_id = contract["version"]["milestones"][0]["id"]
    funding = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": f"{suffix}-fund"},
        json={"provider": "sandbox"},
    )
    assert funding.status_code == 202
    return employer, contract, funding.get_json()


def _capture_payload(intent: dict[str, object], event_id: str) -> tuple[bytes, str]:
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
    return payload, signature


def test_pending_funding_blocks_contract_cancellation(client) -> None:  # type: ignore[no-untyped-def]
    employer, contract, _intent = _active_contract_with_pending_funding(
        client, suffix="pending-cancel"
    )
    cancelled = client.post(
        f"/api/v1/contracts/{contract['id']}/cancel", headers=auth_header(employer)
    )
    assert cancelled.status_code == 409
    stored = db.session.get(Contract, uuid.UUID(contract["id"]))
    assert stored is not None and stored.status == "ACTIVE"


def test_late_capture_cannot_fund_cancelled_contract(client) -> None:  # type: ignore[no-untyped-def]
    _employer, contract, intent = _active_contract_with_pending_funding(
        client, suffix="late-capture"
    )
    stored = db.session.get(Contract, uuid.UUID(contract["id"]))
    assert stored is not None
    stored.status = "CANCELLED"
    db.session.commit()

    payload, signature = _capture_payload(intent, "evt-late-capture")
    captured = client.post(
        "/api/v1/payments/webhooks/sandbox",
        data=payload,
        headers={"X-Payment-Signature": signature, "Content-Type": "application/json"},
    )
    assert captured.status_code == 409
    payment_id = uuid.UUID(intent["payment_intent_id"])
    payment = db.session.get(PaymentIntent, payment_id)
    assert payment is not None and payment.status == "PENDING"
    assert (
        db.session.scalar(
            select(MilestoneFunding.id).where(MilestoneFunding.payment_intent_id == payment_id)
        )
        is None
    )
    assert (
        db.session.scalar(
            select(JournalTransaction.id).where(
                JournalTransaction.operation == "MILESTONE_FUND",
                JournalTransaction.reference_id == str(payment_id),
            )
        )
        is None
    )
