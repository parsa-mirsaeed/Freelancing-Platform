from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.audit.service import record_audit_event
from app.common.outbox import enqueue_outbox_event
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.ledger.models import JournalTransaction, LedgerAccount
from app.ledger.service import (
    Posting,
    get_or_create_account,
    post_journal,
    require_sufficient_balance,
)
from app.payments.idempotency import claim_idempotency, complete_idempotency
from app.payments.models import FinancialIdempotencyKey
from app.payments.providers.base import ProviderTemporaryError
from app.payments.providers.registry import get_provider
from app.payouts.models import Payout
from app.payouts.provider_accounts import resolve_payout_destination


def create_payout(
    *,
    user: User,
    amount_minor: int,
    currency: str,
    provider_name: str,
    idempotency_key: str,
) -> tuple[dict[str, object], int]:
    if amount_minor <= 0:
        raise ApiError("validation_error", "Invalid payout", 422, "amount_minor must be positive")
    currency = currency.strip().upper()
    if len(currency) != 3:
        raise ApiError("validation_error", "Invalid payout", 422, "currency must be 3 letters")
    provider_name = provider_name.strip().lower()

    request_payload: dict[str, object] = {
        "amount_minor": amount_minor,
        "currency": currency,
        "provider": provider_name,
    }
    idem, created = claim_idempotency(
        user_id=user.id,
        operation="payout.create",
        raw_key=idempotency_key,
        request_payload=request_payload,
    )
    if not created and idem.response_body is not None and idem.response_status is not None:
        return idem.response_body, idem.response_status

    payout = db.session.scalar(
        select(Payout).where(Payout.idempotency_key_id == idem.id).with_for_update()
    )
    if payout is not None:
        terminal = _complete_terminal_replay(payout, idem)
        if terminal is not None:
            return terminal
        _upgrade_legacy_destination_snapshot(payout)
    else:
        provider_destination_reference = resolve_payout_destination(
            freelancer_user_id=user.id,
            provider_name=provider_name,
        )
        wallet = db.session.scalar(
            select(LedgerAccount)
            .where(
                LedgerAccount.account_key == f"user:{user.id}:wallet:{currency}",
                LedgerAccount.account_type == "FREELANCER_WALLET",
            )
            .with_for_update()
        )
        if wallet is None:
            raise ApiError("insufficient_funds", "Insufficient funds", 409, "Wallet has no funds")
        require_sufficient_balance(wallet, amount_minor)
        provider_clearing = get_or_create_account(
            account_key=f"provider:{provider_name}:clearing:{currency}",
            account_type="PROVIDER_CLEARING",
            currency=currency,
        )
        payout_id = uuid.uuid4()
        journal = post_journal(
            operation="PAYOUT",
            reference_type="payout",
            reference_id=str(payout_id),
            postings=[
                Posting(wallet, "DEBIT", amount_minor),
                Posting(provider_clearing, "CREDIT", amount_minor),
            ],
            metadata={"provider": provider_name, "freelancer_user_id": str(user.id)},
        )
        payout = Payout(
            id=payout_id,
            freelancer_user_id=user.id,
            idempotency_key_id=idem.id,
            journal_transaction_id=journal.id,
            provider=provider_name,
            provider_destination_reference=provider_destination_reference,
            amount_minor=amount_minor,
            currency=currency,
            status="PENDING",
        )
        db.session.add(payout)
        db.session.flush()
        record_audit_event(
            action="payout.reserved",
            resource_type="payout",
            resource_id=str(payout.id),
            actor_user_id=user.id,
            previous_state={"exists": False},
            new_state=_payout_state(payout),
            metadata={
                "amount_minor": amount_minor,
                "currency": currency,
                "provider": provider_name,
            },
        )
        db.session.commit()

    destination = payout.provider_destination_reference
    if destination is None:
        raise RuntimeError("Pending payout is missing its provider destination snapshot")
    payout_id = payout.id
    provider = get_provider(payout.provider)
    try:
        result = provider.payout(
            user_reference=destination,
            amount_minor=payout.amount_minor,
            currency=payout.currency,
            idempotency_key=idempotency_key,
        )
    except ProviderTemporaryError as exc:
        db.session.rollback()
        persisted = db.session.get(Payout, payout_id)
        if persisted is None:
            raise RuntimeError("Reserved payout disappeared") from exc
        return _pending_payout_body(persisted), 503
    except Exception:
        return _fail_payout(payout_id, actor_user_id=user.id)

    payout = db.session.scalar(select(Payout).where(Payout.id == payout_id).with_for_update())
    if payout is None:
        raise RuntimeError("Reserved payout disappeared")
    if payout.status != "PENDING":
        persisted_idem = db.session.get(FinancialIdempotencyKey, payout.idempotency_key_id)
        if persisted_idem is None:
            raise RuntimeError("Payout lost its idempotency record")
        terminal = _complete_terminal_replay(payout, persisted_idem)
        if terminal is None:
            raise RuntimeError("Payout has an unsupported terminal state")
        return terminal
    if result.amount_minor != payout.amount_minor or result.currency != payout.currency:
        return _fail_payout(payout.id, actor_user_id=user.id)

    previous_state = _payout_state(payout)
    payout.provider_reference = result.reference
    payout.status = "SUCCEEDED"
    payout.completed_at = datetime.now(UTC)
    enqueue_outbox_event(
        event_type="payout.succeeded",
        aggregate_type="payout",
        aggregate_id=str(payout.id),
        payload={"provider_reference": result.reference},
    )
    record_audit_event(
        action="payout.succeeded",
        resource_type="payout",
        resource_id=str(payout.id),
        actor_user_id=user.id,
        previous_state=previous_state,
        new_state=_payout_state(payout),
        metadata={
            "amount_minor": payout.amount_minor,
            "currency": payout.currency,
            "provider": payout.provider,
        },
    )
    persisted_idem = db.session.get(FinancialIdempotencyKey, payout.idempotency_key_id)
    if persisted_idem is None:
        raise RuntimeError("Payout lost its idempotency record")
    body = _serialize_payout(payout)
    complete_idempotency(persisted_idem, status=200, body=body)
    db.session.commit()
    return body, 200


def _upgrade_legacy_destination_snapshot(payout: Payout) -> None:
    if payout.provider_destination_reference is not None:
        return
    if payout.provider != "sandbox":
        raise RuntimeError("Real-provider payout is missing its immutable destination snapshot")
    payout.provider_destination_reference = str(payout.freelancer_user_id)
    db.session.commit()


def _complete_terminal_replay(
    payout: Payout, idem: FinancialIdempotencyKey
) -> tuple[dict[str, object], int] | None:
    if payout.status == "SUCCEEDED":
        body = _serialize_payout(payout)
        complete_idempotency(idem, status=200, body=body)
        db.session.commit()
        return body, 200
    if payout.status == "FAILED":
        body = _failed_payout_body(payout)
        complete_idempotency(idem, status=502, body=body)
        db.session.commit()
        return body, 502
    return None


def _fail_payout(
    payout_id: uuid.UUID, *, actor_user_id: uuid.UUID
) -> tuple[dict[str, object], int]:
    payout = db.session.scalar(select(Payout).where(Payout.id == payout_id).with_for_update())
    if payout is None:
        raise RuntimeError("Reserved payout disappeared")
    if payout.status != "PENDING":
        persisted_idem = db.session.get(FinancialIdempotencyKey, payout.idempotency_key_id)
        if persisted_idem is None:
            raise RuntimeError("Payout lost its idempotency record")
        terminal = _complete_terminal_replay(payout, persisted_idem)
        if terminal is None:
            raise RuntimeError("Payout has an unsupported terminal state")
        return terminal

    previous_state = _payout_state(payout)
    wallet = db.session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.account_key
            == f"user:{payout.freelancer_user_id}:wallet:{payout.currency}"
        )
    )
    provider_clearing = db.session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.account_key == f"provider:{payout.provider}:clearing:{payout.currency}"
        )
    )
    original = db.session.get(JournalTransaction, payout.journal_transaction_id)
    if wallet is None or provider_clearing is None or original is None:
        raise RuntimeError("Payout reservation ledger state is incomplete")
    reversal = post_journal(
        operation="REVERSAL",
        reference_type="payout",
        reference_id=str(payout.id),
        reversal_of_id=original.id,
        postings=[
            Posting(provider_clearing, "DEBIT", payout.amount_minor),
            Posting(wallet, "CREDIT", payout.amount_minor),
        ],
        metadata={"reason": "provider_payout_failed"},
    )
    payout.reversal_journal_transaction_id = reversal.id
    payout.status = "FAILED"
    payout.completed_at = datetime.now(UTC)
    record_audit_event(
        action="payout.failed",
        resource_type="payout",
        resource_id=str(payout.id),
        actor_user_id=actor_user_id,
        previous_state=previous_state,
        new_state=_payout_state(payout),
    )
    persisted_idem = db.session.get(FinancialIdempotencyKey, payout.idempotency_key_id)
    if persisted_idem is None:
        raise RuntimeError("Payout lost its idempotency record")
    body = _failed_payout_body(payout)
    complete_idempotency(persisted_idem, status=502, body=body)
    db.session.commit()
    return body, 502


def _payout_state(payout: Payout) -> dict[str, object]:
    return {
        "status": payout.status,
        "amount_minor": payout.amount_minor,
        "currency": payout.currency,
        "provider": payout.provider,
        "provider_reference_set": payout.provider_reference is not None,
        "destination_snapshot_set": payout.provider_destination_reference is not None,
        "reversal_recorded": payout.reversal_journal_transaction_id is not None,
    }


def _pending_payout_body(payout: Payout) -> dict[str, object]:
    return {
        "type": "payment_provider_temporarily_unavailable",
        "title": "Payment provider temporarily unavailable",
        "status": 503,
        "detail": "Payout outcome is unknown; retry with the same Idempotency-Key",
        "payout_id": str(payout.id),
    }


def _failed_payout_body(payout: Payout) -> dict[str, object]:
    return {
        "type": "payout_failed",
        "title": "Payout failed",
        "status": 502,
        "detail": "The payment provider did not complete the payout; wallet funds were restored",
        "payout_id": str(payout.id),
    }


def _serialize_payout(payout: Payout) -> dict[str, object]:
    return {
        "payout_id": str(payout.id),
        "provider": payout.provider,
        "provider_reference": payout.provider_reference,
        "amount_minor": payout.amount_minor,
        "currency": payout.currency,
        "status": payout.status,
    }
