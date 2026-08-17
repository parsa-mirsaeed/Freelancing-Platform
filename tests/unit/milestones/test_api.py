from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit

_WEBHOOK_SECRET = b"development-only-payment-webhook-secret"


def _active_contract_with_milestone(client):  # type: ignore[no-untyped-def]
    employer = register_user(client, email="milestone-employer@example.com", role="employer")
    freelancer = register_user(client, email="milestone-freelancer@example.com", role="freelancer")
    intruder = register_user(client, email="milestone-intruder@example.com", role="freelancer")
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Milestone project", "description": "Progress", "skills": []},
    ).get_json()
    proposal = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json={
            "amount_minor": 9000,
            "currency": "USD",
            "delivery_days": 9,
            "milestones": [
                {
                    "title": "Delivery",
                    "amount_minor": 9000,
                    "delivery_days": 9,
                }
            ],
        },
    ).get_json()
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/submit",
            headers=auth_header(freelancer),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/accept",
            headers=auth_header(employer),
        ).status_code
        == 200
    )
    contract = client.get(
        f"/api/v1/projects/{project['id']}/contract",
        headers=auth_header(employer),
    ).get_json()
    document_hash = contract["version"]["document_hash"]
    for key, user in (
        ("milestone-sign-employer", employer),
        ("milestone-sign-freelancer", freelancer),
    ):
        response = client.post(
            f"/api/v1/contracts/{contract['id']}/sign",
            headers={**auth_header(user), "Idempotency-Key": key},
            json={"document_hash": document_hash},
        )
        assert response.status_code == 200
        contract = response.get_json()
    assert contract["status"] == "ACTIVE"
    return employer, freelancer, intruder, contract


def _fund(client, employer, milestone_id: str) -> None:  # type: ignore[no-untyped-def]
    response = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": "milestone-fund"},
        json={"provider": "sandbox"},
    )
    assert response.status_code == 202
    intent = response.get_json()
    payload = json.dumps(
        {
            "id": "milestone-fund-captured",
            "type": "payment.captured",
            "data": {
                "provider_reference": intent["provider_reference"],
                "amount_minor": intent["amount_minor"],
                "currency": intent["currency"],
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(_WEBHOOK_SECRET, payload, hashlib.sha256).hexdigest()
    webhook = client.post(
        "/api/v1/payments/webhooks/sandbox",
        data=payload,
        headers={
            "X-Payment-Signature": signature,
            "Content-Type": "application/json",
        },
    )
    assert webhook.status_code == 200


def test_progress_state_machine_is_authorized_and_idempotent(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, freelancer, intruder, contract = _active_contract_with_milestone(client)
    milestone_id = contract["version"]["milestones"][0]["id"]
    _fund(client, employer, milestone_id)

    forbidden = client.post(
        f"/api/v1/milestones/{milestone_id}/start",
        headers=auth_header(intruder),
    )
    assert forbidden.status_code == 403

    started = client.post(
        f"/api/v1/milestones/{milestone_id}/start",
        headers=auth_header(freelancer),
    )
    assert started.status_code == 200
    assert started.get_json()["status"] == "IN_PROGRESS"

    submitted = client.post(
        f"/api/v1/milestones/{milestone_id}/submit",
        headers=auth_header(freelancer),
        json={"note": "first delivery"},
    )
    assert submitted.status_code == 200
    assert submitted.get_json()["status"] == "SUBMITTED"
    assert len(submitted.get_json()["events"]) == 3

    repeated = client.post(
        f"/api/v1/milestones/{milestone_id}/submit",
        headers=auth_header(freelancer),
        json={"note": "duplicate request"},
    )
    assert repeated.status_code == 200
    assert len(repeated.get_json()["events"]) == 3

    changes = client.post(
        f"/api/v1/milestones/{milestone_id}/request-changes",
        headers=auth_header(employer),
        json={"note": "Please adjust validation"},
    )
    assert changes.status_code == 200
    assert changes.get_json()["status"] == "CHANGES_REQUESTED"

    resubmitted = client.post(
        f"/api/v1/milestones/{milestone_id}/submit",
        headers=auth_header(freelancer),
        json={"note": "validation adjusted"},
    )
    assert resubmitted.status_code == 200
    assert resubmitted.get_json()["status"] == "SUBMITTED"

    approved = client.post(
        f"/api/v1/milestones/{milestone_id}/approve",
        headers=auth_header(employer),
    )
    assert approved.status_code == 200
    assert approved.get_json()["status"] == "APPROVED"
    assert len(approved.get_json()["events"]) == 6

    repeated_approval = client.post(
        f"/api/v1/milestones/{milestone_id}/approve",
        headers=auth_header(employer),
    )
    assert repeated_approval.status_code == 200
    assert len(repeated_approval.get_json()["events"]) == 6
