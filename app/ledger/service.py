from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.extensions import db
from app.ledger.models import JournalTransaction, LedgerAccount, LedgerEntry


@dataclass(frozen=True, slots=True)
class Posting:
    account: LedgerAccount
    direction: str
    amount_minor: int


def get_or_create_account(
    *,
    account_key: str,
    account_type: str,
    currency: str,
    owner_user_id: uuid.UUID | None = None,
    milestone_id: uuid.UUID | None = None,
) -> LedgerAccount:
    account = db.session.scalar(
        select(LedgerAccount).where(LedgerAccount.account_key == account_key).with_for_update()
    )
    if account is not None:
        if (
            account.account_type != account_type
            or account.currency != currency
            or account.owner_user_id != owner_user_id
            or account.milestone_id != milestone_id
        ):
            raise RuntimeError("Ledger account key collision with different immutable identity")
        return account
    account = LedgerAccount(
        account_key=account_key,
        account_type=account_type,
        currency=currency,
        owner_user_id=owner_user_id,
        milestone_id=milestone_id,
    )
    try:
        with db.session.begin_nested():
            db.session.add(account)
            db.session.flush()
    except IntegrityError:
        account = db.session.scalar(
            select(LedgerAccount).where(LedgerAccount.account_key == account_key).with_for_update()
        )
        if account is None:
            raise
        if (
            account.account_type != account_type
            or account.currency != currency
            or account.owner_user_id != owner_user_id
            or account.milestone_id != milestone_id
        ):
            raise RuntimeError(
                "Ledger account key collision with different immutable identity"
            ) from None
    return account


def post_journal(
    *,
    operation: str,
    reference_type: str,
    reference_id: str,
    postings: list[Posting],
    metadata: dict[str, object] | None = None,
    reversal_of_id: uuid.UUID | None = None,
) -> JournalTransaction:
    if not postings:
        raise ValueError("A journal requires at least one posting")
    currencies = {posting.account.currency for posting in postings}
    if len(currencies) != 1:
        raise ValueError("All postings in a journal must use one currency")
    currency = next(iter(currencies))
    debit_total = 0
    credit_total = 0
    for posting in postings:
        if posting.amount_minor <= 0:
            raise ValueError("Ledger posting amount must be positive")
        if posting.direction == "DEBIT":
            debit_total += posting.amount_minor
        elif posting.direction == "CREDIT":
            credit_total += posting.amount_minor
        else:
            raise ValueError("Ledger posting direction must be DEBIT or CREDIT")
    if debit_total != credit_total:
        raise ValueError("Ledger journal is unbalanced")

    existing = db.session.scalar(
        select(JournalTransaction).where(
            JournalTransaction.reference_type == reference_type,
            JournalTransaction.reference_id == reference_id,
            JournalTransaction.operation == operation,
        )
    )
    if existing is not None:
        return existing

    journal = JournalTransaction(
        operation=operation,
        reference_type=reference_type,
        reference_id=reference_id,
        reversal_of_id=reversal_of_id,
        metadata_json=metadata or {},
    )
    for posting in postings:
        journal.entries.append(
            LedgerEntry(
                ledger_account_id=posting.account.id,
                direction=posting.direction,
                amount_minor=posting.amount_minor,
                currency=currency,
            )
        )
    db.session.add(journal)
    db.session.flush()
    return journal


def account_balance_minor(account: LedgerAccount) -> int:
    value = db.session.scalar(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (LedgerEntry.direction == "CREDIT", LedgerEntry.amount_minor),
                        else_=-LedgerEntry.amount_minor,
                    )
                ),
                0,
            )
        ).where(LedgerEntry.ledger_account_id == account.id)
    )
    return int(value or 0)


def wallet_balances(user_id: uuid.UUID) -> dict[str, int]:
    rows = db.session.execute(
        select(
            LedgerAccount.currency,
            func.coalesce(
                func.sum(
                    case(
                        (LedgerEntry.direction == "CREDIT", LedgerEntry.amount_minor),
                        else_=-LedgerEntry.amount_minor,
                    )
                ),
                0,
            ),
        )
        .join(LedgerEntry, LedgerEntry.ledger_account_id == LedgerAccount.id)
        .where(
            LedgerAccount.account_type == "FREELANCER_WALLET",
            LedgerAccount.owner_user_id == user_id,
        )
        .group_by(LedgerAccount.currency)
    )
    return {currency: int(balance) for currency, balance in rows}


def require_sufficient_balance(account: LedgerAccount, amount_minor: int) -> None:
    if account_balance_minor(account) < amount_minor:
        raise ApiError(
            "insufficient_funds",
            "Insufficient funds",
            409,
            "Ledger balance is insufficient for this operation",
        )
