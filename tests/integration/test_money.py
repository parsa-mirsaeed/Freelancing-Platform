from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app import create_app
from app.extensions import db
from app.ledger.models import JournalTransaction
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.db

_WEBHOOK_SECRET = b"development-only-payment-webhook-secret"


def _app():  # type: ignore[no-untyped-def]
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "money-integration-secret-key",
            "SQLALCHEMY_DATABASE_URI": os.environ["DATABASE_URL"],
            "REDIS_URL": "redis://localhost:6379/15",
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_INDEX_PREFIX": "money-db-integration-unused",
        }
    )


def _active_milestone(client, *, suffix: str):  # type: ignore[no-untyped-def]
    employer = register_user(client, email=f"money-employer-{suffix}@example.com", role="employer")
    freelancer = register_user(
        client, email=f"money-freelancer-{suffix}@example.com", role="freelancer"
    )
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Money DB", "description": "Concurrency", "skills": []},
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
    return employer, freelancer, contract["version"]["milestones"][0]["id"]


def _fund_and_approve(  # type: ignore[no-untyped-def]
    client, employer, freelancer, milestone_id: str, *, suffix: str
) -> None:
    created = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": f"{suffix}-fund"},
        json={"provider": "sandbox"},
    )
    assert created.status_code == 202
    intent = created.get_json()
    payload = json.dumps(
        {
            "id": f"{suffix}-captured",
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


def test_postgres_rejects_unbalanced_and_mutated_ledger_rows() -> None:
    app = _app()
    account_debit = uuid.uuid4()
    account_credit = uuid.uuid4()
    journal_id = uuid.uuid4()
    with app.app_context():
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ledger_accounts "
                    "(id, account_key, account_type, currency, created_at) VALUES "
                    "(:debit, :debit_key, 'PROVIDER_CLEARING', 'USD', now()), "
                    "(:credit, :credit_key, 'PLATFORM_COMMISSION', 'USD', now())"
                ),
                {
                    "debit": account_debit,
                    "debit_key": f"db-unbalanced-debit-{uuid.uuid4()}",
                    "credit": account_credit,
                    "credit_key": f"db-unbalanced-credit-{uuid.uuid4()}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO journal_transactions "
                    "(id, operation, reference_type, reference_id, metadata_json, created_at) "
                    "VALUES (:id, 'REVERSAL', 'db-test', :reference, '{}'::json, now())"
                ),
                {"id": journal_id, "reference": str(uuid.uuid4())},
            )
            connection.execute(
                text(
                    "INSERT INTO ledger_entries "
                    "(id, journal_transaction_id, ledger_account_id, direction, "
                    "amount_minor, currency, created_at) "
                    "VALUES (:id, :journal, :account, 'DEBIT', 100, 'USD', now())"
                ),
                {"id": uuid.uuid4(), "journal": journal_id, "account": account_debit},
            )

        debit_id = uuid.uuid4()
        credit_id = uuid.uuid4()
        balanced_journal = uuid.uuid4()
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO ledger_accounts "
                    "(id, account_key, account_type, currency, created_at) VALUES "
                    "(:debit, :debit_key, 'PROVIDER_CLEARING', 'USD', now()), "
                    "(:credit, :credit_key, 'PLATFORM_COMMISSION', 'USD', now())"
                ),
                {
                    "debit": debit_id,
                    "debit_key": f"db-immutable-debit-{uuid.uuid4()}",
                    "credit": credit_id,
                    "credit_key": f"db-immutable-credit-{uuid.uuid4()}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO journal_transactions "
                    "(id, operation, reference_type, reference_id, metadata_json, created_at) "
                    "VALUES (:id, 'REVERSAL', 'db-test', :reference, '{}'::json, now())"
                ),
                {"id": balanced_journal, "reference": str(uuid.uuid4())},
            )
            connection.execute(
                text(
                    "INSERT INTO ledger_entries "
                    "(id, journal_transaction_id, ledger_account_id, direction, "
                    "amount_minor, currency, created_at) VALUES "
                    "(:debit_entry, :journal, :debit, 'DEBIT', 100, 'USD', now()), "
                    "(:credit_entry, :journal, :credit, 'CREDIT', 100, 'USD', now())"
                ),
                {
                    "debit_entry": uuid.uuid4(),
                    "credit_entry": uuid.uuid4(),
                    "journal": balanced_journal,
                    "debit": debit_id,
                    "credit": credit_id,
                },
            )
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(
                text("UPDATE journal_transactions SET reference_id = 'tampered' WHERE id = :id"),
                {"id": balanced_journal},
            )


def test_concurrent_release_creates_one_release_journal() -> None:
    app = _app()
    suffix = str(uuid.uuid4())
    with app.test_client() as client:
        employer, freelancer, milestone_id = _active_milestone(client, suffix=suffix)
        _fund_and_approve(client, employer, freelancer, milestone_id, suffix=suffix)

    employer_headers = auth_header(employer)
    barrier = threading.Barrier(2)
    statuses: list[int] = []
    errors: list[BaseException] = []

    def release(key: str) -> None:
        try:
            thread_app = _app()
            with thread_app.test_client() as thread_client:
                barrier.wait()
                response = thread_client.post(
                    f"/api/v1/milestones/{milestone_id}/release",
                    headers={**employer_headers, "Idempotency-Key": key},
                )
                statuses.append(response.status_code)
        except BaseException as exc:  # pragma: no cover - diagnostic capture
            errors.append(exc)

    threads = [
        threading.Thread(target=release, args=(f"{suffix}-release-a",)),
        threading.Thread(target=release, args=(f"{suffix}-release-b",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert sorted(statuses) == [200, 200]
    with app.app_context():
        journals = list(
            db.session.scalars(
                select(JournalTransaction).where(
                    JournalTransaction.operation == "MILESTONE_RELEASE",
                    JournalTransaction.reference_id == milestone_id,
                )
            )
        )
        assert len(journals) == 1
