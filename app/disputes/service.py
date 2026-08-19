from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.common.outbox import enqueue_outbox_event
from app.contracts.models import ContractVersion
from app.disputes.models import (
    DISPUTE_OUTCOMES,
    Dispute,
    DisputeDecision,
    DisputeEvent,
    DisputeEvidence,
    DisputeParty,
)
from app.errors import ApiError
from app.extensions import db
from app.files.models import FileObject
from app.identity.models import User
from app.ledger.models import LedgerAccount
from app.ledger.service import (
    Posting,
    account_balance_minor,
    get_or_create_account,
    post_journal,
)
from app.milestones.models import Milestone, MilestoneEvent
from app.payments.idempotency import claim_idempotency, complete_idempotency
from app.payments.models import MilestoneEscrow, PaymentIntent, Refund
from app.payments.providers.registry import get_provider

_OPENABLE_MILESTONE_STATES = {
    "FUNDED",
    "IN_PROGRESS",
    "SUBMITTED",
    "CHANGES_REQUESTED",
    "APPROVED",
}
_EVIDENCE_STATES = {"OPEN", "EVIDENCE_COLLECTION", "NEED_MORE_INFO"}
_ADMIN_TRANSITIONS = {
    "OPEN": {"EVIDENCE_COLLECTION"},
    "EVIDENCE_COLLECTION": {"UNDER_REVIEW"},
    "UNDER_REVIEW": {"NEED_MORE_INFO"},
    "NEED_MORE_INFO": {"EVIDENCE_COLLECTION", "UNDER_REVIEW"},
}


def open_dispute(*, user: User, milestone_id: uuid.UUID, reason: str) -> Dispute:
    normalized_reason = _required_text(reason, "reason", 4000)
    milestone = _locked_milestone(milestone_id)
    contract = milestone.contract_version.contract
    _require_party(user, contract.employer_user_id, contract.freelancer_user_id)
    if contract.status != "ACTIVE":
        raise ApiError(
            "invalid_state",
            "Contract is not active",
            409,
            "Disputes may only be opened for an active contract",
        )
    if milestone.status not in _OPENABLE_MILESTONE_STATES:
        raise ApiError(
            "invalid_transition",
            "Milestone cannot be disputed",
            409,
            f"Milestone in {milestone.status} cannot enter dispute",
        )
    existing = db.session.scalar(
        select(Dispute).where(Dispute.milestone_id == milestone.id).with_for_update()
    )
    if existing is not None:
        raise ApiError(
            "dispute_exists",
            "Dispute already exists",
            409,
            "A milestone can have only one dispute record",
        )

    before = _state_snapshot(milestone_status=milestone.status, dispute_status=None)
    dispute = Dispute(
        milestone_id=milestone.id,
        contract_id=contract.id,
        opened_by_user_id=user.id,
        status="OPEN",
        reason=normalized_reason,
    )
    dispute.parties.extend(
        [
            DisputeParty(user_id=contract.employer_user_id, role="EMPLOYER"),
            DisputeParty(user_id=contract.freelancer_user_id, role="FREELANCER"),
        ]
    )
    try:
        with db.session.begin_nested():
            db.session.add(dispute)
            db.session.flush()
    except IntegrityError as exc:
        raise ApiError(
            "dispute_exists",
            "Dispute already exists",
            409,
            "A milestone can have only one dispute record",
        ) from exc

    previous_milestone_status = milestone.status
    milestone.status = "DISPUTED"
    milestone.events.append(
        MilestoneEvent(
            actor_user_id=user.id,
            from_status=previous_milestone_status,
            to_status="DISPUTED",
            note="Milestone release frozen by dispute",
        )
    )
    after = _state_snapshot(
        milestone_status=milestone.status,
        dispute_status=dispute.status,
    )
    dispute.events.append(
        DisputeEvent(
            actor_user_id=user.id,
            event_type="OPENED",
            from_status=None,
            to_status="OPEN",
            reason=normalized_reason,
            before_state=before,
            after_state=after,
        )
    )
    _audit_state_change(
        action="dispute.opened",
        dispute=dispute,
        actor_user_id=user.id,
        reason=normalized_reason,
        before=before,
        after=after,
    )
    _notify_other_party(
        dispute=dispute,
        actor_user_id=user.id,
        event_type="dispute.opened",
        title="A dispute was opened",
        body="A funded milestone is frozen while the dispute is reviewed.",
    )
    db.session.commit()
    return dispute


def get_dispute_for_user(*, user: User, dispute_id: uuid.UUID) -> Dispute:
    dispute = _dispute(dispute_id)
    party_ids = {party.user_id for party in dispute.parties}
    if not _is_admin(user) and user.id not in party_ids:
        raise ApiError(
            "forbidden",
            "Forbidden",
            403,
            "Only dispute parties or admins may view it",
        )
    return dispute


def add_evidence(
    *, user: User, dispute_id: uuid.UUID, file_id: uuid.UUID, note: str
) -> DisputeEvidence:
    dispute = _locked_dispute(dispute_id)
    if user.id not in {party.user_id for party in dispute.parties}:
        raise ApiError(
            "forbidden",
            "Forbidden",
            403,
            "Only dispute parties may submit evidence",
        )
    if dispute.status not in _EVIDENCE_STATES:
        raise ApiError(
            "invalid_state",
            "Evidence collection is closed",
            409,
            "Evidence can only be submitted while evidence collection is open",
        )
    normalized_note = note.strip()
    if len(normalized_note) > 4000:
        raise ApiError(
            "validation_error",
            "Invalid note",
            422,
            "note is limited to 4000 chars",
        )

    file_object = db.session.scalar(
        select(FileObject).where(FileObject.id == file_id).with_for_update()
    )
    if file_object is None:
        raise ApiError(
            "file_not_found",
            "File not found",
            404,
            "Evidence file was not found",
        )
    if file_object.owner_user_id != user.id:
        raise ApiError(
            "forbidden",
            "Forbidden",
            403,
            "Evidence must be submitted by its owner",
        )
    if file_object.purpose != "DISPUTE_EVIDENCE" or file_object.status != "SAFE":
        raise ApiError(
            "invalid_evidence_file",
            "Invalid evidence file",
            409,
            "Evidence must use DISPUTE_EVIDENCE purpose and have SAFE scan status",
        )

    before_count = len(dispute.evidence)
    evidence = DisputeEvidence(
        submitted_by_user_id=user.id,
        file_id=file_object.id,
        note=normalized_note,
    )
    dispute.evidence.append(evidence)
    try:
        with db.session.begin_nested():
            db.session.flush()
    except IntegrityError as exc:
        raise ApiError(
            "evidence_exists",
            "Evidence already submitted",
            409,
            "This file is already attached to the dispute",
        ) from exc

    dispute.events.append(
        DisputeEvent(
            actor_user_id=user.id,
            event_type="EVIDENCE_ADDED",
            from_status=dispute.status,
            to_status=dispute.status,
            reason=normalized_note or "Evidence submitted",
            before_state={"evidence_count": before_count},
            after_state={"evidence_count": before_count + 1},
        )
    )
    record_audit_event(
        action="dispute.evidence_added",
        resource_type="dispute",
        resource_id=str(dispute.id),
        actor_user_id=user.id,
        metadata={"file_id": str(file_object.id)},
    )
    db.session.commit()
    return evidence


def admin_transition(
    *, administrator: User, dispute_id: uuid.UUID, to_status: str, reason: str
) -> Dispute:
    _require_admin(administrator)
    dispute = _locked_dispute(dispute_id)
    normalized_status = to_status.strip().upper()
    normalized_reason = _required_text(reason, "reason", 4000)
    allowed = _ADMIN_TRANSITIONS.get(dispute.status, set())
    if normalized_status not in allowed:
        raise ApiError(
            "invalid_transition",
            "Invalid dispute transition",
            409,
            f"Dispute cannot move from {dispute.status} to {normalized_status}",
        )

    milestone_status = _milestone(dispute.milestone_id).status
    before = _state_snapshot(
        milestone_status=milestone_status,
        dispute_status=dispute.status,
    )
    previous = dispute.status
    dispute.status = normalized_status
    after = _state_snapshot(
        milestone_status=milestone_status,
        dispute_status=dispute.status,
    )
    dispute.events.append(
        DisputeEvent(
            actor_user_id=administrator.id,
            event_type="ADMIN_TRANSITION",
            from_status=previous,
            to_status=dispute.status,
            reason=normalized_reason,
            before_state=before,
            after_state=after,
        )
    )
    _audit_state_change(
        action="dispute.transitioned",
        dispute=dispute,
        actor_user_id=administrator.id,
        reason=normalized_reason,
        before=before,
        after=after,
    )
    db.session.commit()
    return dispute


def resolve_dispute(
    *,
    administrator: User,
    dispute_id: uuid.UUID,
    outcome: str,
    reason: str,
    freelancer_award_minor: int | None,
    client_refund_minor: int | None,
    idempotency_key: str,
) -> tuple[dict[str, object], int]:
    _require_admin(administrator)
    dispute = _locked_dispute(dispute_id)
    normalized_outcome = outcome.strip().upper()
    normalized_reason = _required_text(reason, "reason", 4000)
    request_payload: dict[str, object] = {
        "dispute_id": str(dispute.id),
        "outcome": normalized_outcome,
        "reason": normalized_reason,
        "freelancer_award_minor": freelancer_award_minor,
        "client_refund_minor": client_refund_minor,
    }
    idem, created = claim_idempotency(
        user_id=administrator.id,
        operation="dispute.resolve",
        raw_key=idempotency_key,
        request_payload=request_payload,
    )
    if not created and idem.response_body is not None and idem.response_status is not None:
        return idem.response_body, idem.response_status
    _require_reviewable_dispute(dispute)
    if normalized_outcome not in DISPUTE_OUTCOMES:
        raise ApiError(
            "validation_error",
            "Invalid dispute outcome",
            422,
            "outcome must be RELEASE_TO_FREELANCER, REFUND_CLIENT, or SPLIT",
        )

    milestone = _locked_milestone(dispute.milestone_id)
    if milestone.status != "DISPUTED":
        raise ApiError(
            "invalid_state",
            "Milestone is not disputed",
            409,
            "Dispute resolution requires the milestone release to remain frozen",
        )
    escrow, escrow_account = _locked_funded_escrow(milestone)
    funded_minor = account_balance_minor(escrow_account)
    award_minor, refund_minor = _resolution_amounts(
        outcome=normalized_outcome,
        funded_minor=funded_minor,
        freelancer_award_minor=freelancer_award_minor,
        client_refund_minor=client_refund_minor,
    )
    commission_minor = award_minor * escrow.commission_bps // 10000
    freelancer_net_minor = award_minor - commission_minor

    contract = milestone.contract_version.contract
    postings = [Posting(escrow_account, "DEBIT", funded_minor)]
    _append_freelancer_postings(
        postings=postings,
        freelancer_user_id=contract.freelancer_user_id,
        currency=milestone.currency,
        freelancer_net_minor=freelancer_net_minor,
        commission_minor=commission_minor,
    )
    refund_provider: str | None = None
    refund_reference: str | None = None
    if refund_minor:
        refund_provider, refund_reference = _confirm_provider_refund(
            dispute=dispute,
            milestone=milestone,
            refund_minor=refund_minor,
            idempotency_key=idempotency_key,
            postings=postings,
        )

    journal = post_journal(
        operation="DISPUTE_RESOLUTION",
        reference_type="dispute",
        reference_id=str(dispute.id),
        postings=postings,
        metadata={
            "milestone_id": str(milestone.id),
            "outcome": normalized_outcome,
            "freelancer_award_minor": award_minor,
            "client_refund_minor": refund_minor,
            "commission_minor": commission_minor,
        },
    )
    refund = _persist_resolution_refund(
        milestone=milestone,
        employer_user_id=contract.employer_user_id,
        idempotency_key_id=idem.id,
        journal_id=journal.id,
        refund_minor=refund_minor,
        provider=refund_provider,
        provider_reference=refund_reference,
    )

    before = _state_snapshot(
        milestone_status=milestone.status,
        dispute_status=dispute.status,
    )
    milestone.events.append(
        MilestoneEvent(
            actor_user_id=administrator.id,
            from_status="DISPUTED",
            to_status="RELEASED",
            note=f"Dispute resolved with outcome {normalized_outcome}",
        )
    )
    milestone.status = "RELEASED"
    dispute.status = "RESOLVED"
    dispute.resolved_at = datetime.now(UTC)
    dispute.decision = DisputeDecision(
        administrator_user_id=administrator.id,
        outcome=normalized_outcome,
        freelancer_award_minor=award_minor,
        freelancer_net_minor=freelancer_net_minor,
        client_refund_minor=refund_minor,
        commission_minor=commission_minor,
        currency=milestone.currency,
        journal_transaction_id=journal.id,
        refund_id=refund.id if refund is not None else None,
        reason=normalized_reason,
    )
    db.session.flush()

    after = _state_snapshot(
        milestone_status=milestone.status,
        dispute_status=dispute.status,
        outcome=normalized_outcome,
    )
    dispute.events.append(
        DisputeEvent(
            actor_user_id=administrator.id,
            event_type="RESOLVED",
            from_status="UNDER_REVIEW",
            to_status="RESOLVED",
            reason=normalized_reason,
            before_state=before,
            after_state=after,
        )
    )
    _audit_state_change(
        action="dispute.resolved",
        dispute=dispute,
        actor_user_id=administrator.id,
        reason=normalized_reason,
        before=before,
        after=after,
        extra={
            "journal_transaction_id": str(journal.id),
            "outcome": normalized_outcome,
            "freelancer_award_minor": award_minor,
            "client_refund_minor": refund_minor,
            "commission_minor": commission_minor,
        },
    )
    _notify_all_parties(
        dispute=dispute,
        event_type="dispute.resolved",
        title="Dispute resolved",
        body=f"The dispute was resolved with outcome {normalized_outcome}.",
    )
    db.session.flush()
    response = serialize_dispute(dispute)
    complete_idempotency(idem, status=200, body=response)
    db.session.commit()
    return response, 200


def serialize_dispute(dispute: Dispute) -> dict[str, Any]:
    decision = dispute.decision
    return {
        "id": str(dispute.id),
        "milestone_id": str(dispute.milestone_id),
        "contract_id": str(dispute.contract_id),
        "opened_by_user_id": str(dispute.opened_by_user_id),
        "status": dispute.status,
        "reason": dispute.reason,
        "created_at": dispute.created_at.isoformat(),
        "resolved_at": dispute.resolved_at.isoformat() if dispute.resolved_at else None,
        "parties": [
            {"user_id": str(party.user_id), "role": party.role} for party in dispute.parties
        ],
        "evidence": [_serialize_evidence(item) for item in dispute.evidence],
        "events": [_serialize_event(item) for item in dispute.events],
        "decision": _serialize_decision(decision) if decision is not None else None,
    }


def _serialize_evidence(item: DisputeEvidence) -> dict[str, object]:
    return {
        "id": str(item.id),
        "file_id": str(item.file_id),
        "submitted_by_user_id": str(item.submitted_by_user_id),
        "note": item.note,
        "created_at": item.created_at.isoformat(),
    }


def _serialize_event(item: DisputeEvent) -> dict[str, object]:
    return {
        "event_type": item.event_type,
        "from_status": item.from_status,
        "to_status": item.to_status,
        "reason": item.reason,
        "created_at": item.created_at.isoformat(),
    }


def _serialize_decision(decision: DisputeDecision) -> dict[str, object]:
    return {
        "id": str(decision.id),
        "administrator_user_id": str(decision.administrator_user_id),
        "outcome": decision.outcome,
        "freelancer_award_minor": decision.freelancer_award_minor,
        "freelancer_net_minor": decision.freelancer_net_minor,
        "client_refund_minor": decision.client_refund_minor,
        "commission_minor": decision.commission_minor,
        "currency": decision.currency,
        "journal_transaction_id": str(decision.journal_transaction_id),
        "refund_id": str(decision.refund_id) if decision.refund_id else None,
        "reason": decision.reason,
        "created_at": decision.created_at.isoformat(),
    }


def _require_reviewable_dispute(dispute: Dispute) -> None:
    if dispute.status == "RESOLVED" or dispute.decision is not None:
        raise ApiError(
            "dispute_already_resolved",
            "Dispute already resolved",
            409,
            "A resolved dispute cannot be decided again",
        )
    if dispute.status != "UNDER_REVIEW":
        raise ApiError(
            "invalid_transition",
            "Dispute is not under review",
            409,
            "Dispute resolution requires UNDER_REVIEW status",
        )


def _locked_funded_escrow(
    milestone: Milestone,
) -> tuple[MilestoneEscrow, LedgerAccount]:
    escrow = db.session.scalar(
        select(MilestoneEscrow)
        .where(MilestoneEscrow.milestone_id == milestone.id)
        .with_for_update()
    )
    if escrow is None:
        raise ApiError(
            "escrow_not_found",
            "Escrow not found",
            409,
            "Milestone has not been funded",
        )
    account = db.session.scalar(
        select(LedgerAccount).where(LedgerAccount.id == escrow.escrow_account_id).with_for_update()
    )
    if account is None:
        raise RuntimeError("Escrow references a missing ledger account")
    balance = account_balance_minor(account)
    if balance != milestone.amount_minor or balance <= 0:
        raise ApiError(
            "escrow_not_fully_funded",
            "Escrow is not fully funded",
            409,
            "Dispute resolution requires the full contracted amount to remain in escrow",
        )
    return escrow, account


def _append_freelancer_postings(
    *,
    postings: list[Posting],
    freelancer_user_id: uuid.UUID,
    currency: str,
    freelancer_net_minor: int,
    commission_minor: int,
) -> None:
    if freelancer_net_minor:
        wallet = get_or_create_account(
            account_key=f"user:{freelancer_user_id}:wallet:{currency}",
            account_type="FREELANCER_WALLET",
            owner_user_id=freelancer_user_id,
            currency=currency,
        )
        postings.append(Posting(wallet, "CREDIT", freelancer_net_minor))
    if commission_minor:
        platform = get_or_create_account(
            account_key=f"platform:commission:{currency}",
            account_type="PLATFORM_COMMISSION",
            currency=currency,
        )
        postings.append(Posting(platform, "CREDIT", commission_minor))


def _confirm_provider_refund(
    *,
    dispute: Dispute,
    milestone: Milestone,
    refund_minor: int,
    idempotency_key: str,
    postings: list[Posting],
) -> tuple[str, str]:
    intent = _captured_funding_intent(milestone.id)
    if intent.provider_reference is None:
        raise RuntimeError("Captured funding payment is missing its provider reference")
    provider = get_provider(intent.provider)
    provider_key = hashlib.sha256(f"dispute:{dispute.id}:{idempotency_key}".encode()).hexdigest()
    result = provider.refund(
        reference=intent.provider_reference,
        amount_minor=refund_minor,
        currency=milestone.currency,
        idempotency_key=provider_key,
    )
    if (
        result.status != "SUCCEEDED"
        or result.amount_minor != refund_minor
        or result.currency != milestone.currency
    ):
        raise ApiError(
            "refund_failed",
            "Refund failed",
            502,
            "Payment provider did not confirm the dispute refund",
        )
    provider_clearing = get_or_create_account(
        account_key=f"provider:{intent.provider}:clearing:{milestone.currency}",
        account_type="PROVIDER_CLEARING",
        currency=milestone.currency,
    )
    postings.append(Posting(provider_clearing, "CREDIT", refund_minor))
    return intent.provider, result.reference


def _persist_resolution_refund(
    *,
    milestone: Milestone,
    employer_user_id: uuid.UUID,
    idempotency_key_id: uuid.UUID,
    journal_id: uuid.UUID,
    refund_minor: int,
    provider: str | None,
    provider_reference: str | None,
) -> Refund | None:
    if not refund_minor:
        return None
    if provider is None or provider_reference is None:
        raise RuntimeError("Confirmed refund lost provider metadata")
    refund = Refund(
        milestone_id=milestone.id,
        employer_user_id=employer_user_id,
        journal_transaction_id=journal_id,
        idempotency_key_id=idempotency_key_id,
        provider=provider,
        provider_reference=provider_reference,
        amount_minor=refund_minor,
        currency=milestone.currency,
        status="SUCCEEDED",
    )
    db.session.add(refund)
    db.session.flush()
    return refund


def _resolution_amounts(
    *,
    outcome: str,
    funded_minor: int,
    freelancer_award_minor: int | None,
    client_refund_minor: int | None,
) -> tuple[int, int]:
    if outcome == "RELEASE_TO_FREELANCER":
        invalid_award = freelancer_award_minor not in (None, funded_minor)
        invalid_refund = client_refund_minor not in (None, 0)
        if invalid_award or invalid_refund:
            raise ApiError(
                "validation_error",
                "Invalid release amounts",
                422,
                "RELEASE_TO_FREELANCER must award the entire funded amount",
            )
        return funded_minor, 0
    if outcome == "REFUND_CLIENT":
        invalid_award = freelancer_award_minor not in (None, 0)
        invalid_refund = client_refund_minor not in (None, funded_minor)
        if invalid_award or invalid_refund:
            raise ApiError(
                "validation_error",
                "Invalid refund amounts",
                422,
                "REFUND_CLIENT must refund the entire funded amount",
            )
        return 0, funded_minor
    if freelancer_award_minor is None or client_refund_minor is None:
        raise ApiError(
            "validation_error",
            "Split amounts required",
            422,
            "SPLIT requires freelancer_award_minor and client_refund_minor",
        )
    if freelancer_award_minor <= 0 or client_refund_minor <= 0:
        raise ApiError(
            "validation_error",
            "Invalid split amounts",
            422,
            "SPLIT allocations must both be positive",
        )
    if freelancer_award_minor + client_refund_minor != funded_minor:
        raise ApiError(
            "validation_error",
            "Split does not balance",
            422,
            "SPLIT allocations must total exactly the funded escrow amount",
        )
    return freelancer_award_minor, client_refund_minor


def _required_text(value: str, field: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise ApiError(
            "validation_error",
            f"Invalid {field}",
            422,
            f"{field} must contain 1 to {max_length} characters",
        )
    return normalized


def _require_party(user: User, employer_id: uuid.UUID, freelancer_id: uuid.UUID) -> None:
    if user.id not in {employer_id, freelancer_id}:
        raise ApiError(
            "forbidden",
            "Forbidden",
            403,
            "Only contract parties may open a dispute",
        )


def _require_admin(user: User) -> None:
    if not _is_admin(user):
        raise ApiError(
            "forbidden",
            "Forbidden",
            403,
            "Administrator permission is required",
        )


def _is_admin(user: User) -> bool:
    return "admin" in {assignment.role for assignment in user.roles}


def _dispute_query() -> Select[tuple[Dispute]]:
    return select(Dispute).options(
        selectinload(Dispute.parties),
        selectinload(Dispute.evidence),
        selectinload(Dispute.events),
        selectinload(Dispute.decision),
    )


def _dispute(dispute_id: uuid.UUID) -> Dispute:
    dispute = db.session.scalar(_dispute_query().where(Dispute.id == dispute_id))
    if dispute is None:
        raise ApiError(
            "dispute_not_found",
            "Dispute not found",
            404,
            "Dispute was not found",
        )
    return dispute


def _locked_dispute(dispute_id: uuid.UUID) -> Dispute:
    dispute = db.session.scalar(_dispute_query().where(Dispute.id == dispute_id).with_for_update())
    if dispute is None:
        raise ApiError(
            "dispute_not_found",
            "Dispute not found",
            404,
            "Dispute was not found",
        )
    return dispute


def _milestone_query() -> Select[tuple[Milestone]]:
    return select(Milestone).options(
        selectinload(Milestone.contract_version).selectinload(ContractVersion.contract),
        selectinload(Milestone.events),
    )


def _milestone(milestone_id: uuid.UUID) -> Milestone:
    milestone = db.session.scalar(_milestone_query().where(Milestone.id == milestone_id))
    if milestone is None:
        raise ApiError(
            "milestone_not_found",
            "Milestone not found",
            404,
            "Milestone was not found",
        )
    return milestone


def _locked_milestone(milestone_id: uuid.UUID) -> Milestone:
    milestone = db.session.scalar(
        _milestone_query().where(Milestone.id == milestone_id).with_for_update()
    )
    if milestone is None:
        raise ApiError(
            "milestone_not_found",
            "Milestone not found",
            404,
            "Milestone was not found",
        )
    return milestone


def _captured_funding_intent(milestone_id: uuid.UUID) -> PaymentIntent:
    intent = db.session.scalar(
        select(PaymentIntent)
        .where(
            PaymentIntent.milestone_id == milestone_id,
            PaymentIntent.status == "CAPTURED",
        )
        .order_by(PaymentIntent.captured_at.desc())
        .with_for_update()
    )
    if intent is None:
        raise RuntimeError("Funded milestone has no captured provider payment")
    return intent


def _state_snapshot(
    *, milestone_status: str, dispute_status: str | None, outcome: str | None = None
) -> dict[str, object]:
    state: dict[str, object] = {
        "milestone_status": milestone_status,
        "status": dispute_status,
    }
    if outcome is not None:
        state["outcome"] = outcome
    return state


def _audit_state_change(
    *,
    action: str,
    dispute: Dispute,
    actor_user_id: uuid.UUID,
    reason: str,
    before: dict[str, object],
    after: dict[str, object],
    extra: dict[str, object] | None = None,
) -> None:
    metadata: dict[str, object] = {
        "who": str(actor_user_id),
        "what": action,
        "when": datetime.now(UTC).isoformat(),
        "why": reason,
        "before": before,
        "after": after,
    }
    if extra:
        metadata.update(extra)
    record_audit_event(
        action=action,
        resource_type="dispute",
        resource_id=str(dispute.id),
        actor_user_id=actor_user_id,
        metadata=metadata,
    )


def _notify_other_party(
    *,
    dispute: Dispute,
    actor_user_id: uuid.UUID,
    event_type: str,
    title: str,
    body: str,
) -> None:
    for party in dispute.parties:
        if party.user_id != actor_user_id:
            _notification_event(
                user_id=party.user_id,
                dispute=dispute,
                event_type=event_type,
                title=title,
                body=body,
            )


def _notify_all_parties(*, dispute: Dispute, event_type: str, title: str, body: str) -> None:
    for party in dispute.parties:
        _notification_event(
            user_id=party.user_id,
            dispute=dispute,
            event_type=event_type,
            title=title,
            body=body,
        )


def _notification_event(
    *,
    user_id: uuid.UUID,
    dispute: Dispute,
    event_type: str,
    title: str,
    body: str,
) -> None:
    enqueue_outbox_event(
        event_type="notification.requested",
        aggregate_type="dispute",
        aggregate_id=str(dispute.id),
        payload={
            "user_id": str(user_id),
            "event_type": event_type,
            "title": title,
            "body": body,
            "payload": {"dispute_id": str(dispute.id)},
            "dedupe_key": f"{event_type}:{dispute.id}:{user_id}",
        },
    )
