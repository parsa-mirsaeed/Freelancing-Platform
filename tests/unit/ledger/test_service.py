from __future__ import annotations

import uuid

import pytest

from app.extensions import db
from app.ledger.models import JournalTransaction, LedgerEntry
from app.ledger.service import Posting, get_or_create_account, post_journal

pytestmark = pytest.mark.unit


def test_post_journal_requires_balanced_single_currency_entries(
    app,  # type: ignore[no-untyped-def]
) -> None:
    with app.app_context():
        debit = get_or_create_account(
            account_key="test:debit:USD",
            account_type="PROVIDER_CLEARING",
            currency="USD",
        )
        credit = get_or_create_account(
            account_key="test:credit:USD",
            account_type="PLATFORM_COMMISSION",
            currency="USD",
        )
        with pytest.raises(ValueError, match="balanced"):
            post_journal(
                operation="REVERSAL",
                reference_type="unit",
                reference_id=str(uuid.uuid4()),
                postings=[
                    Posting(debit, "DEBIT", 100),
                    Posting(credit, "CREDIT", 99),
                ],
            )
        db.session.rollback()

        journal = post_journal(
            operation="REVERSAL",
            reference_type="unit",
            reference_id=str(uuid.uuid4()),
            postings=[
                Posting(debit, "DEBIT", 100),
                Posting(credit, "CREDIT", 100),
            ],
        )
        db.session.commit()
        assert (
            sum(entry.amount_minor for entry in journal.entries if entry.direction == "DEBIT")
            == 100
        )
        assert (
            sum(entry.amount_minor for entry in journal.entries if entry.direction == "CREDIT")
            == 100
        )


def test_committed_ledger_rows_are_immutable(app) -> None:  # type: ignore[no-untyped-def]
    with app.app_context():
        debit = get_or_create_account(
            account_key="immutability:debit:USD",
            account_type="PROVIDER_CLEARING",
            currency="USD",
        )
        credit = get_or_create_account(
            account_key="immutability:credit:USD",
            account_type="PLATFORM_COMMISSION",
            currency="USD",
        )
        journal = post_journal(
            operation="REVERSAL",
            reference_type="unit",
            reference_id="immutable-ledger",
            postings=[
                Posting(debit, "DEBIT", 100),
                Posting(credit, "CREDIT", 100),
            ],
        )
        db.session.commit()

        persisted = db.session.get(JournalTransaction, journal.id)
        assert persisted is not None
        persisted.reference_id = "tampered"
        with pytest.raises(ValueError, match="immutable"):
            db.session.commit()
        db.session.rollback()

        entry = db.session.get(LedgerEntry, journal.entries[0].id)
        assert entry is not None
        entry.amount_minor = 999
        with pytest.raises(ValueError, match="immutable"):
            db.session.commit()
        db.session.rollback()
