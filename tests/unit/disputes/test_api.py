from __future__ import annotations

import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select

from app.audit.models import AuditEvent
from app.disputes.models import Dispute
from app.extensions import db
from app.files.models import FileObject
from app.identity.models import UserRole
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit
_WEBHOOK_SECRET = b"development-only-payment-webhook-secret"


def _admin(client):  # type: ignore[no-untyped-def]
    admin = register_user(
        client,
        email=f"dispute-admin-{uuid.uuid4()}@example.com",
        role="employer",
    )
    with client.application.app_context():
        db.session.add(UserRole(user_id=uuid.UUID(admin["user"]["id"]), role="admin"))
        db.session.commit()
    return admin


def _funded_approved_milestone(client, *, suffix: str):  # type: ignore[no-untyped-def]
    employer = register_user(
        client,
        email=f"{suffix}-employer@example.com",
        role="employer",
    )
    freelancer = register_user(
        client,
        email=f"{suffix}-freelancer@example.com",
        role="freelancer",
    )
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Dispute project", "description": "Resolution", "skills": []},
    ).get_json()
    proposal = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json={
            "amount_minor": 10000,
            "currency": "USD",
            "delivery_days": 5,
            "milestones": [{"title": "Delivery", "amount_minor": 10000, "delivery_days": 5}],
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
        (f"{suffix}-employer", employer),
        (f"{suffix}-freelancer", freelancer),
    ):
        assert (
            client.post(
                f"/api/v1/contracts/{contract['id']}/sign",
                headers={**auth_header(user), "Idempotency-Key": key},
                json={"document_hash": document_hash},
            ).status_code
            == 200
        )
    milestone_id = contract["version"]["milestones"][0]["id"]
    funding = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": f"{suffix}-fund"},
        json={"provider": "sandbox"},
    )
    assert funding.status_code == 202
    intent = funding.get_json()
    payload = json.dumps(
        {
            "id": f"{suffix}-captured",
            "type": "payment.captured",
            "data": {
                "reference": intent["provider_reference"],
                "amount_minor": 10000,
                "currency": "USD",
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.new(_WEBHOOK_SECRET, payload, hashlib.sha256).hexdigest()
    assert (
        client.post(
            "/api/v1/payments/webhooks/sandbox",
            data=payload,
            headers={
                "X-Payment-Signature": signature,
                "Content-Type": "application/json",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/milestones/{milestone_id}/start",
            headers=auth_header(freelancer),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/milestones/{milestone_id}/submit",
            headers=auth_header(freelancer),
            json={"note": "delivered"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/milestones/{milestone_id}/approve",
            headers=auth_header(employer),
        ).status_code
        == 200
    )
    return employer, freelancer, milestone_id


def _open_and_review(client, *, suffix: str):  # type: ignore[no-untyped-def]
    employer, freelancer, milestone_id = _funded_approved_milestone(
        client,
        suffix=suffix,
    )
    opened = client.post(
        f"/api/v1/milestones/{milestone_id}/disputes",
        headers=auth_header(employer),
        json={"reason": "Delivery does not match the agreed scope"},
    )
    assert opened.status_code == 201
    dispute = opened.get_json()
    admin = _admin(client)
    for status in ("EVIDENCE_COLLECTION", "UNDER_REVIEW"):
        transitioned = client.post(
            f"/api/v1/disputes/{dispute['id']}/transitions",
            headers=auth_header(admin),
            json={"to_status": status, "reason": f"Move to {status}"},
        )
        assert transitioned.status_code == 200
        dispute = transitioned.get_json()
    return employer, freelancer, admin, milestone_id, dispute


def test_opening_dispute_freezes_release(client) -> None:  # type: ignore[no-untyped-def]
    employer, _freelancer, milestone_id = _funded_approved_milestone(
        client,
        suffix="freeze",
    )
    opened = client.post(
        f"/api/v1/milestones/{milestone_id}/disputes",
        headers=auth_header(employer),
        json={"reason": "Freeze before release"},
    )
    assert opened.status_code == 201
    assert opened.get_json()["status"] == "OPEN"
    release = client.post(
        f"/api/v1/milestones/{milestone_id}/release",
        headers={**auth_header(employer), "Idempotency-Key": "freeze-release"},
    )
    assert release.status_code == 409


def test_non_party_cannot_add_evidence(
    client,
    app,  # type: ignore[no-untyped-def]
) -> None:
    employer, _freelancer, milestone_id = _funded_approved_milestone(
        client,
        suffix="evidence",
    )
    opened = client.post(
        f"/api/v1/milestones/{milestone_id}/disputes",
        headers=auth_header(employer),
        json={"reason": "Collect evidence"},
    ).get_json()
    intruder = register_user(
        client,
        email="dispute-intruder@example.com",
        role="employer",
    )
    with app.app_context():
        file_object = FileObject(
            owner_user_id=uuid.UUID(intruder["user"]["id"]),
            object_key=f"quarantine/{uuid.uuid4()}/evidence.pdf",
            original_name="evidence.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            purpose="DISPUTE_EVIDENCE",
            status="SAFE",
        )
        db.session.add(file_object)
        db.session.commit()
        file_id = file_object.id
    response = client.post(
        f"/api/v1/disputes/{opened['id']}/evidence",
        headers=auth_header(intruder),
        json={"file_id": str(file_id), "note": "not my dispute"},
    )
    assert response.status_code == 403


def test_split_is_exact_admin_audited_and_cannot_resolve_twice(
    client,
    app,  # type: ignore[no-untyped-def]
) -> None:
    _employer, _freelancer, admin, _milestone_id, dispute = _open_and_review(
        client,
        suffix="split",
    )
    mismatch = client.post(
        f"/api/v1/disputes/{dispute['id']}/resolve",
        headers={**auth_header(admin), "Idempotency-Key": "split-mismatch"},
        json={
            "outcome": "SPLIT",
            "reason": "Incorrect arithmetic should fail",
            "freelancer_award_minor": 6000,
            "client_refund_minor": 3000,
        },
    )
    assert mismatch.status_code == 422

    resolved = client.post(
        f"/api/v1/disputes/{dispute['id']}/resolve",
        headers={**auth_header(admin), "Idempotency-Key": "split-correct"},
        json={
            "outcome": "SPLIT",
            "reason": "Evidence supports a sixty-forty split",
            "freelancer_award_minor": 6000,
            "client_refund_minor": 4000,
        },
    )
    assert resolved.status_code == 200
    body = resolved.get_json()
    assert body["status"] == "RESOLVED"
    assert body["decision"]["outcome"] == "SPLIT"
    assert body["decision"]["freelancer_award_minor"] == 6000
    assert body["decision"]["client_refund_minor"] == 4000

    second = client.post(
        f"/api/v1/disputes/{dispute['id']}/resolve",
        headers={**auth_header(admin), "Idempotency-Key": "split-second"},
        json={"outcome": "REFUND_CLIENT", "reason": "not allowed"},
    )
    assert second.status_code == 409

    with app.app_context():
        dispute_row = db.session.scalar(
            select(Dispute).where(Dispute.id == uuid.UUID(dispute["id"]))
        )
        assert dispute_row is not None and dispute_row.decision is not None
        audits = list(
            db.session.scalars(
                select(AuditEvent).where(
                    AuditEvent.resource_type == "dispute",
                    AuditEvent.resource_id == dispute["id"],
                    AuditEvent.action == "dispute.resolved",
                )
            )
        )
        assert len(audits) == 1
        metadata = audits[0].metadata_json
        assert metadata["who"] == admin["user"]["id"]
        assert metadata["why"] == "Evidence supports a sixty-forty split"
        assert metadata["before"]["status"] == "UNDER_REVIEW"
        assert metadata["after"]["status"] == "RESOLVED"
