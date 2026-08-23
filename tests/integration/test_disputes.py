from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import uuid

import pytest
from sqlalchemy import select

from app import create_app
from app.disputes.models import Dispute
from app.extensions import db
from app.identity.mfa import totp_code_for_secret
from app.identity.models import UserRole
from app.ledger.models import JournalTransaction, LedgerEntry
from app.milestones.models import Milestone
from app.payments.models import MilestoneEscrow, Refund
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.db
_WEBHOOK_SECRET = b"development-only-payment-webhook-secret"


def _app():  # type: ignore[no-untyped-def]
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "dispute-integration-secret-key",
            "SQLALCHEMY_DATABASE_URI": os.environ["DATABASE_URL"],
            "REDIS_URL": "redis://localhost:6379/15",
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_INDEX_PREFIX": "dispute-db-integration-unused",
        }
    )


def _funded_approved_milestone(client, *, suffix: str):  # type: ignore[no-untyped-def]
    employer = register_user(
        client,
        email=f"dispute-db-employer-{suffix}@example.com",
        role="employer",
    )
    freelancer = register_user(
        client,
        email=f"dispute-db-freelancer-{suffix}@example.com",
        role="freelancer",
    )
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Dispute DB", "description": "Concurrency", "skills": []},
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
    for key, user in ((f"{suffix}-employer", employer), (f"{suffix}-freelancer", freelancer)):
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
            "id": f"{suffix}-capture",
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
            headers={"X-Payment-Signature": signature, "Content-Type": "application/json"},
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
            json={"note": "done"},
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


def _admin(client, *, suffix: str):  # type: ignore[no-untyped-def]
    admin = register_user(
        client,
        email=f"dispute-db-admin-{suffix}@example.com",
        role="employer",
    )
    with client.application.app_context():
        db.session.add(UserRole(user_id=uuid.UUID(admin["user"]["id"]), role="admin"))
        db.session.commit()
    enrolled = client.post(
        "/api/v1/auth/mfa/totp/enroll",
        headers=auth_header(admin),
        json={"password": "correct horse battery staple"},
    )
    assert enrolled.status_code == 200
    confirmed = client.post(
        "/api/v1/auth/mfa/totp/confirm",
        headers=auth_header(admin),
        json={"code": totp_code_for_secret(enrolled.get_json()["secret"])},
    )
    assert confirmed.status_code == 200
    return admin


def test_open_dispute_and_release_are_serialized_by_postgres() -> None:
    app = _app()
    suffix = str(uuid.uuid4())
    with app.test_client() as client:
        employer, _freelancer, milestone_id = _funded_approved_milestone(client, suffix=suffix)

    headers = auth_header(employer)
    barrier = threading.Barrier(2)
    results: list[tuple[str, int]] = []
    errors: list[BaseException] = []

    def release() -> None:
        try:
            thread_app = _app()
            with thread_app.test_client() as client:
                barrier.wait()
                response = client.post(
                    f"/api/v1/milestones/{milestone_id}/release",
                    headers={**headers, "Idempotency-Key": f"{suffix}-release"},
                )
                results.append(("release", response.status_code))
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    def dispute() -> None:
        try:
            thread_app = _app()
            with thread_app.test_client() as client:
                barrier.wait()
                response = client.post(
                    f"/api/v1/milestones/{milestone_id}/disputes",
                    headers=headers,
                    json={"reason": "Race release with dispute freeze"},
                )
                results.append(("dispute", response.status_code))
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    threads = [threading.Thread(target=release), threading.Thread(target=dispute)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors
    assert len(results) == 2
    by_name = dict(results)
    assert by_name["release"] in {200, 409}
    assert by_name["dispute"] in {201, 409}
    assert 409 in by_name.values()
    assert {by_name["release"], by_name["dispute"]} & {200, 201}

    with app.app_context():
        milestone_uuid = uuid.UUID(milestone_id)
        dispute_row = db.session.scalar(
            select(Dispute).where(Dispute.milestone_id == milestone_uuid)
        )
        release_journals = list(
            db.session.scalars(
                select(JournalTransaction).where(
                    JournalTransaction.operation == "MILESTONE_RELEASE",
                    JournalTransaction.reference_id == milestone_id,
                )
            )
        )
        milestone = db.session.get(Milestone, milestone_uuid)
        assert milestone is not None
        if dispute_row is not None:
            assert release_journals == []
            assert milestone.status == "DISPUTED"
        else:
            assert len(release_journals) == 1
            assert milestone.status == "RELEASED"


def test_split_resolution_is_one_balanced_terminal_ledger_transaction() -> None:
    app = _app()
    suffix = str(uuid.uuid4())
    with app.test_client() as client:
        employer, _freelancer, milestone_id = _funded_approved_milestone(client, suffix=suffix)
        dispute = client.post(
            f"/api/v1/milestones/{milestone_id}/disputes",
            headers=auth_header(employer),
            json={"reason": "Split after evidence review"},
        ).get_json()
        admin = _admin(client, suffix=suffix)
        for status in ("EVIDENCE_COLLECTION", "UNDER_REVIEW"):
            assert (
                client.post(
                    f"/api/v1/disputes/{dispute['id']}/transitions",
                    headers=auth_header(admin),
                    json={"to_status": status, "reason": f"Move to {status}"},
                ).status_code
                == 200
            )
        response = client.post(
            f"/api/v1/disputes/{dispute['id']}/resolve",
            headers={**auth_header(admin), "Idempotency-Key": f"{suffix}-split"},
            json={
                "outcome": "SPLIT",
                "reason": "Six thousand awarded and four thousand refunded",
                "freelancer_award_minor": 6000,
                "client_refund_minor": 4000,
            },
        )
        assert response.status_code == 200

    with app.app_context():
        dispute_uuid = uuid.UUID(dispute["id"])
        journal = db.session.scalar(
            select(JournalTransaction).where(
                JournalTransaction.operation == "DISPUTE_RESOLUTION",
                JournalTransaction.reference_type == "dispute",
                JournalTransaction.reference_id == str(dispute_uuid),
            )
        )
        assert journal is not None
        entries = list(
            db.session.scalars(
                select(LedgerEntry).where(LedgerEntry.journal_transaction_id == journal.id)
            )
        )
        debits = sum(entry.amount_minor for entry in entries if entry.direction == "DEBIT")
        credits = sum(entry.amount_minor for entry in entries if entry.direction == "CREDIT")
        assert debits == credits == 10000
        refund = db.session.scalar(
            select(Refund).where(Refund.journal_transaction_id == journal.id)
        )
        assert refund is not None
        assert refund.amount_minor == 4000
        escrow = db.session.scalar(
            select(MilestoneEscrow).where(MilestoneEscrow.milestone_id == uuid.UUID(milestone_id))
        )
        assert escrow is not None
        escrow_entries = list(
            db.session.scalars(
                select(LedgerEntry).where(LedgerEntry.ledger_account_id == escrow.escrow_account_id)
            )
        )
        balance = sum(
            entry.amount_minor if entry.direction == "CREDIT" else -entry.amount_minor
            for entry in escrow_entries
        )
        assert balance == 0
        milestone = db.session.get(Milestone, uuid.UUID(milestone_id))
        assert milestone is not None and milestone.status == "RELEASED"
