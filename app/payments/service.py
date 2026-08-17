from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.common.outbox import enqueue_outbox_event
from app.contracts.models import Contract, ContractVersion
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.ledger.models import JournalTransaction, LedgerAccount
from app.ledger.service import Posting, account_balance_minor, get_or_create_account, post_journal
from app.milestones.models import Milestone, MilestoneEvent
from app.payments.idempotency import claim_idempotency, complete_idempotency
from app.payments.models import (
    FinancialIdempotencyKey,
    MilestoneEscrow,
    MilestoneFunding,
    PaymentIntent,
    ProviderEvent,
    ReconciliationRun,
    Refund,
)
from app.payments.policies import can_fund_milestone, can_release_or_refund
from app.payments.providers.registry import get_provider


def fund_milestone(
    *, user: User, milestone_id: uuid.UUID, provider_name: str, idempotency_key: str
) -> tuple[dict[str, object], int]:
    milestone = _locked_milestone(milestone_id)
    contract = _locked_contract(milestone.contract_version.contract_id)
    _require_active_contract(contract.status)
    if not can_fund_milestone(user, contract):
        raise ApiError("forbidden", "Forbidden", 403, "Only the employer party may fund escrow")
    provider_name = provider_name.strip().lower()
    idem, created = claim_idempotency(
        user_id=user.id,
        operation="milestone.fund",
        raw_key=idempotency_key,
        request_payload={"milestone_id": str(milestone.id), "provider": provider_name},
    )
    if not created and idem.response_body is not None and idem.response_status is not None:
        return idem.response_body, idem.response_status
    if milestone.status != "CREATED":
        raise ApiError(
            "invalid_transition",
            "Invalid milestone transition",
            409,
            f"Milestone in {milestone.status} cannot be funded",
        )
    existing = db.session.scalar(
        select(PaymentIntent).where(PaymentIntent.idempotency_key_id == idem.id)
    )
    if existing is not None:
        body = _serialize_payment_intent(existing)
        status = 200 if existing.status == "CAPTURED" else 202
        complete_idempotency(idem, status=status, body=body)
        db.session.commit()
        return body, status

    provider = get_provider(provider_name)
    result = provider.create_payment(
        amount_minor=milestone.amount_minor,
        currency=milestone.currency,
        idempotency_key=idempotency_key,
    )
    intent = PaymentIntent(
        milestone_id=milestone.id,
        employer_user_id=user.id,
        provider=provider.name,
        provider_reference=result.reference,
        idempotency_key_id=idem.id,
        amount_minor=milestone.amount_minor,
        currency=milestone.currency,
        status="PENDING",
    )
    db.session.add(intent)
    db.session.flush()
    record_audit_event(
        action="payment.created",
        resource_type="payment_intent",
        resource_id=str(intent.id),
        actor_user_id=user.id,
        metadata={
            "milestone_id": str(milestone.id),
            "provider": provider.name,
            "amount_minor": intent.amount_minor,
            "currency": intent.currency,
        },
    )
    body = _serialize_payment_intent(intent)
    complete_idempotency(idem, status=202, body=body)
    db.session.commit()
    return body, 202


def process_provider_webhook(
    *, provider_name: str, payload: bytes, signature: str
) -> tuple[dict[str, object], int]:
    provider = get_provider(provider_name)
    verified = provider.verify_webhook(payload=payload, signature=signature)
    payload_hash = hashlib.sha256(payload).hexdigest()
    existing = db.session.scalar(
        select(ProviderEvent).where(
            ProviderEvent.provider == provider.name,
            ProviderEvent.external_event_id == verified.external_event_id,
        )
    )
    if existing is not None:
        return _duplicate_provider_event(existing, payload_hash)

    event = ProviderEvent(
        provider=provider.name,
        external_event_id=verified.external_event_id,
        event_type=verified.event_type,
        payload_hash=payload_hash,
    )
    try:
        with db.session.begin_nested():
            db.session.add(event)
            db.session.flush()
    except IntegrityError:
        existing = db.session.scalar(
            select(ProviderEvent).where(
                ProviderEvent.provider == provider.name,
                ProviderEvent.external_event_id == verified.external_event_id,
            )
        )
        if existing is None:
            raise
        return _duplicate_provider_event(existing, payload_hash)

    if verified.event_type == "payment.captured":
        provider_reference = _webhook_string(verified.data, "provider_reference")
        amount_minor = _webhook_int(verified.data, "amount_minor")
        currency = _webhook_string(verified.data, "currency").upper()
        intent = db.session.scalar(
            select(PaymentIntent)
            .where(
                PaymentIntent.provider == provider.name,
                PaymentIntent.provider_reference == provider_reference,
            )
            .with_for_update()
        )
        if intent is None:
            raise ApiError(
                "payment_not_found",
                "Payment not found",
                404,
                "Webhook payment reference is unknown",
            )
        if intent.amount_minor != amount_minor or intent.currency != currency:
            raise ApiError(
                "payment_mismatch",
                "Payment mismatch",
                409,
                "Webhook amount or currency differs from the stored payment intent",
            )
        _capture_intent(intent=intent, actor_user_id=None)
    elif verified.event_type == "payment.failed":
        provider_reference = _webhook_string(verified.data, "provider_reference")
        intent = db.session.scalar(
            select(PaymentIntent)
            .where(
                PaymentIntent.provider == provider.name,
                PaymentIntent.provider_reference == provider_reference,
            )
            .with_for_update()
        )
        if intent is not None and intent.status != "CAPTURED":
            intent.status = "FAILED"

    event.processed_at = datetime.now(UTC)
    db.session.commit()
    return {"status": "processed", "event_id": event.external_event_id}, 200


def release_milestone(
    *, user: User, milestone_id: uuid.UUID, idempotency_key: str
) -> tuple[dict[str, object], int]:
    milestone = _locked_milestone(milestone_id)
    contract = milestone.contract_version.contract
    _require_active_contract(contract.status)
    if not can_release_or_refund(user, contract):
        raise ApiError("forbidden", "Forbidden", 403, "Only the employer party may release escrow")
    idem, created = claim_idempotency(
        user_id=user.id,
        operation="milestone.release",
        raw_key=idempotency_key,
        request_payload={"milestone_id": str(milestone.id)},
    )
    if not created and idem.response_body is not None and idem.response_status is not None:
        return idem.response_body, idem.response_status
    if milestone.status == "RELEASED":
        body = _financial_state(milestone)
        complete_idempotency(idem, status=200, body=body)
        db.session.commit()
        return body, 200
    if milestone.status != "APPROVED":
        raise ApiError(
            "invalid_transition",
            "Invalid milestone transition",
            409,
            "Milestone must be approved before escrow is released",
        )

    escrow = _require_escrow(milestone.id)
    escrow_account = db.session.scalar(
        select(LedgerAccount).where(LedgerAccount.id == escrow.escrow_account_id).with_for_update()
    )
    if escrow_account is None:
        raise RuntimeError("Escrow references a missing ledger account")
    balance = account_balance_minor(escrow_account)
    if balance != milestone.amount_minor:
        raise ApiError(
            "escrow_not_fully_funded",
            "Escrow is not fully funded",
            409,
            "Release requires the full contracted milestone amount in escrow",
        )

    wallet = get_or_create_account(
        account_key=f"user:{contract.freelancer_user_id}:wallet:{milestone.currency}",
        account_type="FREELANCER_WALLET",
        owner_user_id=contract.freelancer_user_id,
        currency=milestone.currency,
    )
    platform = get_or_create_account(
        account_key=f"platform:commission:{milestone.currency}",
        account_type="PLATFORM_COMMISSION",
        currency=milestone.currency,
    )
    fee_minor = milestone.amount_minor * escrow.commission_bps // 10000
    freelancer_minor = milestone.amount_minor - fee_minor
    postings = [
        Posting(escrow_account, "DEBIT", milestone.amount_minor),
        Posting(wallet, "CREDIT", freelancer_minor),
    ]
    if fee_minor:
        postings.append(Posting(platform, "CREDIT", fee_minor))
    journal = post_journal(
        operation="MILESTONE_RELEASE",
        reference_type="milestone",
        reference_id=str(milestone.id),
        postings=postings,
        metadata={
            "commission_bps": escrow.commission_bps,
            "commission_minor": fee_minor,
            "freelancer_user_id": str(contract.freelancer_user_id),
        },
    )
    milestone.events.append(
        MilestoneEvent(
            actor_user_id=user.id,
            from_status="APPROVED",
            to_status="RELEASE_PENDING",
            note="Escrow release journal created",
        )
    )
    milestone.status = "RELEASE_PENDING"
    milestone.events.append(
        MilestoneEvent(
            actor_user_id=user.id,
            from_status="RELEASE_PENDING",
            to_status="RELEASED",
            note="Internal ledger release committed",
        )
    )
    milestone.status = "RELEASED"
    enqueue_outbox_event(
        event_type="milestone.released",
        aggregate_type="milestone",
        aggregate_id=str(milestone.id),
        payload={"journal_transaction_id": str(journal.id)},
    )
    record_audit_event(
        action="milestone.released",
        resource_type="milestone",
        resource_id=str(milestone.id),
        actor_user_id=user.id,
        metadata={
            "journal_transaction_id": str(journal.id),
            "amount_minor": milestone.amount_minor,
            "currency": milestone.currency,
            "commission_minor": fee_minor,
        },
    )
    body = _financial_state(milestone)
    complete_idempotency(idem, status=200, body=body)
    db.session.commit()
    return body, 200


def refund_milestone(
    *, user: User, milestone_id: uuid.UUID, provider_name: str, idempotency_key: str
) -> tuple[dict[str, object], int]:
    milestone = _locked_milestone(milestone_id)
    contract = milestone.contract_version.contract
    _require_active_contract(contract.status)
    if not can_release_or_refund(user, contract):
        raise ApiError("forbidden", "Forbidden", 403, "Only the employer party may refund escrow")
    provider_name = provider_name.strip().lower()
    idem, created = claim_idempotency(
        user_id=user.id,
        operation="milestone.refund",
        raw_key=idempotency_key,
        request_payload={"milestone_id": str(milestone.id), "provider": provider_name},
    )
    if not created and idem.response_body is not None and idem.response_status is not None:
        return idem.response_body, idem.response_status

    refund = db.session.scalar(
        select(Refund).where(Refund.idempotency_key_id == idem.id).with_for_update()
    )
    if refund is not None:
        terminal = _complete_refund_replay(refund, idem)
        if terminal is not None:
            return terminal
        funding_intent = _captured_funding_intent(
            milestone_id=refund.milestone_id, provider_name=refund.provider
        )
    else:
        if milestone.status != "FUNDED":
            raise ApiError(
                "invalid_transition",
                "Invalid milestone transition",
                409,
                "Refund is only available before milestone work starts",
            )
        escrow = _require_escrow(milestone.id)
        escrow_account = db.session.scalar(
            select(LedgerAccount)
            .where(LedgerAccount.id == escrow.escrow_account_id)
            .with_for_update()
        )
        if escrow_account is None:
            raise RuntimeError("Escrow references a missing ledger account")
        amount_minor = account_balance_minor(escrow_account)
        if amount_minor <= 0:
            raise ApiError(
                "nothing_to_refund",
                "Nothing to refund",
                409,
                "Escrow has no refundable funds",
            )
        funding_intent = _captured_funding_intent(
            milestone_id=milestone.id, provider_name=provider_name
        )
        provider_clearing = get_or_create_account(
            account_key=f"provider:{provider_name}:clearing:{milestone.currency}",
            account_type="PROVIDER_CLEARING",
            currency=milestone.currency,
        )
        refund_id = uuid.uuid4()
        journal = post_journal(
            operation="MILESTONE_REFUND",
            reference_type="refund",
            reference_id=str(refund_id),
            postings=[
                Posting(escrow_account, "DEBIT", amount_minor),
                Posting(provider_clearing, "CREDIT", amount_minor),
            ],
            metadata={"milestone_id": str(milestone.id), "provider": provider_name},
        )
        refund = Refund(
            id=refund_id,
            milestone_id=milestone.id,
            employer_user_id=user.id,
            journal_transaction_id=journal.id,
            idempotency_key_id=idem.id,
            provider=provider_name,
            amount_minor=amount_minor,
            currency=milestone.currency,
            status="PENDING",
        )
        db.session.add(refund)
        db.session.flush()
        record_audit_event(
            action="refund.reserved",
            resource_type="refund",
            resource_id=str(refund.id),
            actor_user_id=user.id,
            metadata={
                "milestone_id": str(milestone.id),
                "amount_minor": refund.amount_minor,
                "currency": refund.currency,
                "provider": refund.provider,
            },
        )
        db.session.commit()

    if funding_intent.provider_reference is None:
        raise RuntimeError("Captured funding payment is missing its provider reference")
    provider = get_provider(refund.provider)
    try:
        result = provider.refund(
            reference=funding_intent.provider_reference,
            amount_minor=refund.amount_minor,
            currency=refund.currency,
            idempotency_key=idempotency_key,
        )
    except Exception:
        return _fail_refund(refund.id, actor_user_id=user.id)

    refund = db.session.scalar(select(Refund).where(Refund.id == refund.id).with_for_update())
    milestone = _locked_milestone(milestone_id)
    if refund is None:
        raise RuntimeError("Reserved refund disappeared")
    if refund.status != "PENDING":
        persisted_idem = db.session.get(FinancialIdempotencyKey, refund.idempotency_key_id)
        if persisted_idem is None:
            raise RuntimeError("Refund lost its idempotency record")
        terminal = _complete_refund_replay(refund, persisted_idem)
        if terminal is None:
            raise RuntimeError("Refund has an unsupported terminal state")
        return terminal
    if result.amount_minor != refund.amount_minor or result.currency != refund.currency:
        return _fail_refund(refund.id, actor_user_id=user.id)
    if milestone.status != "FUNDED":
        raise RuntimeError("Pending refund milestone left the FUNDED state")

    refund.provider_reference = result.reference
    refund.status = "SUCCEEDED"
    milestone.status = "CREATED"
    milestone.events.append(
        MilestoneEvent(
            actor_user_id=user.id,
            from_status="FUNDED",
            to_status="CREATED",
            note="Escrow funding fully refunded before work started",
        )
    )
    enqueue_outbox_event(
        event_type="milestone.refunded",
        aggregate_type="milestone",
        aggregate_id=str(milestone.id),
        payload={"refund_id": str(refund.id)},
    )
    record_audit_event(
        action="milestone.refunded",
        resource_type="refund",
        resource_id=str(refund.id),
        actor_user_id=user.id,
        metadata={
            "milestone_id": str(milestone.id),
            "amount_minor": refund.amount_minor,
            "currency": refund.currency,
        },
    )
    persisted_idem = db.session.get(FinancialIdempotencyKey, refund.idempotency_key_id)
    if persisted_idem is None:
        raise RuntimeError("Refund lost its idempotency record")
    body = _serialize_refund(refund)
    complete_idempotency(persisted_idem, status=200, body=body)
    db.session.commit()
    return body, 200


def _captured_funding_intent(*, milestone_id: uuid.UUID, provider_name: str) -> PaymentIntent:
    intent = db.session.scalar(
        select(PaymentIntent)
        .where(
            PaymentIntent.milestone_id == milestone_id,
            PaymentIntent.status == "CAPTURED",
            PaymentIntent.provider == provider_name,
        )
        .order_by(PaymentIntent.captured_at.desc())
    )
    if intent is None:
        raise ApiError(
            "refund_provider_mismatch",
            "Refund provider mismatch",
            409,
            "No captured funding payment exists for this provider",
        )
    return intent


def get_milestone_financial_state(*, user: User, milestone_id: uuid.UUID) -> dict[str, object]:
    milestone = _milestone(milestone_id)
    contract = milestone.contract_version.contract
    if user.id not in {contract.employer_user_id, contract.freelancer_user_id}:
        raise ApiError("forbidden", "Forbidden", 403, "Only contract parties may view escrow state")
    return _financial_state(milestone)


def require_milestone_fully_funded(milestone: Milestone) -> None:
    escrow = _require_escrow(milestone.id)
    account = db.session.get(LedgerAccount, escrow.escrow_account_id)
    if account is None or account_balance_minor(account) != milestone.amount_minor:
        raise ApiError(
            "escrow_not_fully_funded",
            "Escrow is not fully funded",
            409,
            "Milestone work cannot start until the full contracted amount is in escrow",
        )


def reconcile_provider(provider_name: str) -> ReconciliationRun:
    provider = get_provider(provider_name)
    run = ReconciliationRun(provider=provider.name, status="RUNNING")
    db.session.add(run)
    db.session.flush()
    discrepancies: list[dict[str, object]] = []
    intents = list(
        db.session.scalars(
            select(PaymentIntent).where(
                PaymentIntent.provider == provider.name,
                PaymentIntent.status == "CAPTURED",
            )
        )
    )
    for intent in intents:
        run.checked_count += 1
        if intent.provider_reference is None:
            discrepancies.append(
                {"payment_intent_id": str(intent.id), "reason": "missing_reference"}
            )
            continue
        remote = provider.get_transaction(reference=intent.provider_reference)
        funding = db.session.scalar(
            select(MilestoneFunding).where(MilestoneFunding.payment_intent_id == intent.id)
        )
        if (
            funding is None
            or remote.amount_minor != intent.amount_minor
            or remote.currency != intent.currency
            or remote.status not in {"CAPTURED", "SUCCEEDED"}
        ):
            discrepancies.append(
                {
                    "payment_intent_id": str(intent.id),
                    "provider_reference": intent.provider_reference,
                    "reason": "provider_or_ledger_mismatch",
                }
            )
    run.discrepancy_count = len(discrepancies)
    run.details = {"discrepancies": discrepancies}
    run.status = "MISMATCH" if discrepancies else "SUCCEEDED"
    run.completed_at = datetime.now(UTC)
    if discrepancies:
        enqueue_outbox_event(
            event_type="payments.reconciliation_mismatch",
            aggregate_type="reconciliation_run",
            aggregate_id=str(run.id),
            payload={"provider": provider.name, "count": len(discrepancies)},
        )
    record_audit_event(
        action="payments.reconciled",
        resource_type="reconciliation_run",
        resource_id=str(run.id),
        metadata={
            "provider": provider.name,
            "checked_count": run.checked_count,
            "discrepancy_count": run.discrepancy_count,
        },
    )
    db.session.commit()
    return run


def _capture_intent(*, intent: PaymentIntent, actor_user_id: uuid.UUID | None) -> dict[str, object]:
    if intent.status == "CAPTURED":
        return _financial_state(_milestone(intent.milestone_id))
    milestone = _locked_milestone(intent.milestone_id)
    contract = _locked_contract(milestone.contract_version.contract_id)
    _require_active_contract(contract.status)
    if milestone.status not in {"CREATED", "FUNDED"}:
        raise ApiError(
            "invalid_transition",
            "Invalid milestone transition",
            409,
            f"Captured payment cannot fund milestone in {milestone.status}",
        )
    if intent.provider_reference is None:
        raise RuntimeError("Captured payment intent is missing provider reference")
    escrow = _escrow_for_milestone(milestone.id)
    if escrow is None:
        escrow_account = get_or_create_account(
            account_key=f"milestone:{milestone.id}:escrow:{milestone.currency}",
            account_type="MILESTONE_ESCROW",
            milestone_id=milestone.id,
            currency=milestone.currency,
        )
        escrow = MilestoneEscrow(
            milestone_id=milestone.id,
            escrow_account_id=escrow_account.id,
            commission_bps=_contract_commission_bps(milestone),
        )
        db.session.add(escrow)
        db.session.flush()
    else:
        existing_escrow_account = db.session.get(LedgerAccount, escrow.escrow_account_id)
        if existing_escrow_account is None:
            raise RuntimeError("Escrow references a missing ledger account")
        escrow_account = existing_escrow_account
    before = account_balance_minor(escrow_account)
    if before + intent.amount_minor > milestone.amount_minor:
        raise ApiError(
            "escrow_overfund",
            "Escrow overfunding rejected",
            409,
            "Captured amount would exceed the contracted milestone amount",
        )
    provider_clearing = get_or_create_account(
        account_key=f"provider:{intent.provider}:clearing:{intent.currency}",
        account_type="PROVIDER_CLEARING",
        currency=intent.currency,
    )
    journal = post_journal(
        operation="MILESTONE_FUND",
        reference_type="payment_intent",
        reference_id=str(intent.id),
        postings=[
            Posting(provider_clearing, "DEBIT", intent.amount_minor),
            Posting(escrow_account, "CREDIT", intent.amount_minor),
        ],
        metadata={
            "provider": intent.provider,
            "provider_reference": intent.provider_reference,
            "milestone_id": str(milestone.id),
        },
    )
    if (
        db.session.scalar(
            select(MilestoneFunding).where(MilestoneFunding.payment_intent_id == intent.id)
        )
        is None
    ):
        db.session.add(
            MilestoneFunding(
                escrow_id=escrow.id,
                payment_intent_id=intent.id,
                journal_transaction_id=journal.id,
                amount_minor=intent.amount_minor,
            )
        )
    intent.status = "CAPTURED"
    intent.captured_at = datetime.now(UTC)
    after = before + intent.amount_minor
    if after == milestone.amount_minor and milestone.status != "FUNDED":
        previous = milestone.status
        milestone.status = "FUNDED"
        milestone.events.append(
            MilestoneEvent(
                actor_user_id=actor_user_id,
                from_status=previous,
                to_status="FUNDED",
                note="Full contracted milestone amount captured into escrow",
            )
        )
    enqueue_outbox_event(
        event_type="milestone.funded",
        aggregate_type="milestone",
        aggregate_id=str(milestone.id),
        payload={
            "payment_intent_id": str(intent.id),
            "journal_transaction_id": str(journal.id),
            "funded_balance_minor": after,
        },
    )
    record_audit_event(
        action="milestone.funded",
        resource_type="milestone",
        resource_id=str(milestone.id),
        actor_user_id=actor_user_id,
        metadata={
            "payment_intent_id": str(intent.id),
            "journal_transaction_id": str(journal.id),
            "amount_minor": intent.amount_minor,
            "currency": intent.currency,
        },
    )
    return _financial_state(milestone)


def _complete_refund_replay(
    refund: Refund, idem: FinancialIdempotencyKey
) -> tuple[dict[str, object], int] | None:
    if refund.status == "SUCCEEDED":
        body = _serialize_refund(refund)
        complete_idempotency(idem, status=200, body=body)
        db.session.commit()
        return body, 200
    if refund.status == "FAILED":
        body = _failed_refund_body(refund)
        complete_idempotency(idem, status=502, body=body)
        db.session.commit()
        return body, 502
    return None


def _fail_refund(
    refund_id: uuid.UUID, *, actor_user_id: uuid.UUID
) -> tuple[dict[str, object], int]:
    refund = db.session.scalar(select(Refund).where(Refund.id == refund_id).with_for_update())
    if refund is None:
        raise RuntimeError("Reserved refund disappeared")
    if refund.status != "PENDING":
        persisted_idem = db.session.get(FinancialIdempotencyKey, refund.idempotency_key_id)
        if persisted_idem is None:
            raise RuntimeError("Refund lost its idempotency record")
        terminal = _complete_refund_replay(refund, persisted_idem)
        if terminal is None:
            raise RuntimeError("Refund has an unsupported terminal state")
        return terminal
    journal = db.session.get(JournalTransaction, refund.journal_transaction_id)
    escrow = _require_escrow(refund.milestone_id)
    escrow_account = db.session.get(LedgerAccount, escrow.escrow_account_id)
    provider_account = db.session.scalar(
        select(LedgerAccount).where(
            LedgerAccount.account_key == f"provider:{refund.provider}:clearing:{refund.currency}"
        )
    )
    if journal is None or escrow_account is None or provider_account is None:
        raise RuntimeError("Refund reservation ledger state is incomplete")
    post_journal(
        operation="REVERSAL",
        reference_type="refund",
        reference_id=str(refund.id),
        reversal_of_id=journal.id,
        postings=[
            Posting(provider_account, "DEBIT", refund.amount_minor),
            Posting(escrow_account, "CREDIT", refund.amount_minor),
        ],
        metadata={"reason": "provider_refund_failed"},
    )
    refund.status = "FAILED"
    record_audit_event(
        action="refund.failed",
        resource_type="refund",
        resource_id=str(refund.id),
        actor_user_id=actor_user_id,
    )
    persisted_idem = db.session.get(FinancialIdempotencyKey, refund.idempotency_key_id)
    if persisted_idem is None:
        raise RuntimeError("Refund lost its idempotency record")
    body = _failed_refund_body(refund)
    complete_idempotency(persisted_idem, status=502, body=body)
    db.session.commit()
    return body, 502


def _failed_refund_body(refund: Refund) -> dict[str, object]:
    return {
        "type": "refund_failed",
        "title": "Refund failed",
        "status": 502,
        "detail": "The payment provider did not complete the refund; escrow funds were restored",
        "refund_id": str(refund.id),
    }


def _financial_state(milestone: Milestone) -> dict[str, object]:
    escrow = _escrow_for_milestone(milestone.id)
    return {
        "milestone_id": str(milestone.id),
        "milestone_status": milestone.status,
        "contracted_amount_minor": milestone.amount_minor,
        "currency": milestone.currency,
        "escrow_balance_minor": _escrow_balance(escrow),
        "commission_bps": escrow.commission_bps if escrow is not None else None,
    }


def _serialize_payment_intent(intent: PaymentIntent) -> dict[str, object]:
    return {
        "payment_intent_id": str(intent.id),
        "milestone_id": str(intent.milestone_id),
        "provider": intent.provider,
        "provider_reference": intent.provider_reference,
        "amount_minor": intent.amount_minor,
        "currency": intent.currency,
        "status": intent.status,
    }


def _serialize_refund(refund: Refund) -> dict[str, object]:
    return {
        "refund_id": str(refund.id),
        "milestone_id": str(refund.milestone_id),
        "provider": refund.provider,
        "provider_reference": refund.provider_reference,
        "amount_minor": refund.amount_minor,
        "currency": refund.currency,
        "status": refund.status,
    }


def _contract_commission_bps(milestone: Milestone) -> int:
    commission = milestone.contract_version.snapshot.get("commission")
    if commission is None:
        return 0
    if not isinstance(commission, dict):
        raise RuntimeError("Contract commission snapshot must be an object")
    value = commission.get("platform_bps")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 10000:
        raise RuntimeError("Contract commission platform_bps is invalid")
    return value


def _require_active_contract(status: str) -> None:
    if status != "ACTIVE":
        raise ApiError(
            "invalid_state",
            "Contract is not active",
            409,
            "Financial milestone operations require an active contract",
        )


def _milestone_query() -> Select[tuple[Milestone]]:
    return select(Milestone).options(
        selectinload(Milestone.contract_version).selectinload(ContractVersion.contract),
        selectinload(Milestone.events),
    )


def _milestone(milestone_id: uuid.UUID) -> Milestone:
    milestone = db.session.scalar(_milestone_query().where(Milestone.id == milestone_id))
    if milestone is None:
        raise ApiError("milestone_not_found", "Milestone not found", 404, "Milestone was not found")
    return milestone


def _locked_milestone(milestone_id: uuid.UUID) -> Milestone:
    milestone = db.session.scalar(
        _milestone_query().where(Milestone.id == milestone_id).with_for_update()
    )
    if milestone is None:
        raise ApiError("milestone_not_found", "Milestone not found", 404, "Milestone was not found")
    return milestone


def _locked_contract(contract_id: uuid.UUID) -> Contract:
    contract = db.session.scalar(
        select(Contract).where(Contract.id == contract_id).with_for_update()
    )
    if contract is None:
        raise RuntimeError("Milestone references a missing contract")
    return contract


def _escrow_for_milestone(milestone_id: uuid.UUID) -> MilestoneEscrow | None:
    return db.session.scalar(
        select(MilestoneEscrow).where(MilestoneEscrow.milestone_id == milestone_id)
    )


def _require_escrow(milestone_id: uuid.UUID) -> MilestoneEscrow:
    escrow = _escrow_for_milestone(milestone_id)
    if escrow is None:
        raise ApiError("escrow_not_found", "Escrow not found", 409, "Milestone has not been funded")
    return escrow


def _escrow_balance(escrow: MilestoneEscrow | None) -> int:
    if escrow is None:
        return 0
    account = db.session.get(LedgerAccount, escrow.escrow_account_id)
    if account is None:
        raise RuntimeError("Escrow references a missing ledger account")
    return account_balance_minor(account)


def _duplicate_provider_event(
    event: ProviderEvent, payload_hash: str
) -> tuple[dict[str, object], int]:
    if event.payload_hash != payload_hash:
        raise ApiError(
            "provider_event_conflict",
            "Provider event conflict",
            409,
            "The provider reused an event id with a different payload",
        )
    return {"status": "duplicate", "event_id": event.external_event_id}, 200


def _webhook_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ApiError("invalid_webhook", "Invalid webhook", 400, f"Webhook {key} is required")
    return value


def _webhook_int(data: dict[str, object], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(
            "invalid_webhook", "Invalid webhook", 400, f"Webhook {key} must be an integer"
        )
    return value
