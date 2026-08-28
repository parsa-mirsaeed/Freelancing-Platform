from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.contracts.models import Contract, ContractParty, ContractSignature, ContractVersion
from app.contracts.policies import can_cancel_contract, is_contract_party
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.milestones.models import Milestone
from app.projects.models import Project, ProjectAttachment
from app.proposals.models import Proposal, ProposalVersion

SNAPSHOT_SCHEMA_VERSION = 2


def get_contract(contract_id: uuid.UUID) -> Contract:
    contract = db.session.scalar(_contract_query().where(Contract.id == contract_id))
    if contract is None:
        raise ApiError("contract_not_found", "Contract not found", 404, "Contract was not found")
    return contract


def get_project_contract(project_id: uuid.UUID) -> Contract:
    contract = db.session.scalar(_contract_query().where(Contract.project_id == project_id))
    if contract is None:
        raise ApiError("contract_not_found", "Contract not found", 404, "Project has no contract")
    return contract


def get_contract_for_user(*, user: User, contract_id: uuid.UUID) -> Contract:
    contract = get_contract(contract_id)
    if not is_contract_party(user, contract):
        raise ApiError(
            "forbidden", "Forbidden", 403, "Only contract parties may view this contract"
        )
    return contract


def get_project_contract_for_user(*, user: User, project_id: uuid.UUID) -> Contract:
    contract = get_project_contract(project_id)
    if not is_contract_party(user, contract):
        raise ApiError(
            "forbidden", "Forbidden", 403, "Only contract parties may view this contract"
        )
    return contract


def create_contract_from_accepted_proposal(
    *, proposal: Proposal, project: Project, actor_user_id: uuid.UUID
) -> Contract:
    existing = db.session.scalar(select(Contract).where(Contract.project_id == project.id))
    if existing is not None:
        if existing.accepted_proposal_id == proposal.id:
            return existing
        raise ApiError(
            "contract_exists",
            "Contract already exists",
            409,
            "A project may have at most one contract",
        )

    proposal_version = _current_proposal_version(proposal)
    milestone_terms = _milestone_terms(proposal_version)
    attachments = list(
        db.session.scalars(
            select(ProjectAttachment)
            .where(ProjectAttachment.project_id == project.id)
            .order_by(ProjectAttachment.object_key.asc())
        )
    )
    snapshot = _build_snapshot(
        project=project,
        proposal=proposal,
        proposal_version=proposal_version,
        milestone_terms=milestone_terms,
        attachments=attachments,
    )
    version = ContractVersion(
        version_number=1,
        snapshot=snapshot,
        document_hash=_document_hash(snapshot),
    )
    contract = Contract(
        project_id=project.id,
        accepted_proposal_id=proposal.id,
        employer_user_id=project.employer_user_id,
        freelancer_user_id=proposal.freelancer_user_id,
        status="PENDING_SIGNATURES",
        current_version=1,
    )
    contract.versions.append(version)
    contract.parties.extend(
        [
            ContractParty(
                user_id=project.employer_user_id,
                role="EMPLOYER",
                required_signature=True,
            ),
            ContractParty(
                user_id=proposal.freelancer_user_id,
                role="FREELANCER",
                required_signature=True,
            ),
        ]
    )
    version.milestones.extend(
        Milestone(
            sequence=sequence,
            title=title,
            amount_minor=amount_minor,
            currency=proposal_version.currency,
            delivery_days=delivery_days,
            status="CREATED",
        )
        for sequence, title, amount_minor, delivery_days in milestone_terms
    )
    db.session.add(contract)
    db.session.flush()
    record_audit_event(
        action="contract.created",
        resource_type="contract",
        resource_id=str(contract.id),
        actor_user_id=actor_user_id,
        previous_state={"exists": False},
        new_state=_contract_state(contract, version),
        metadata={
            "project_id": str(project.id),
            "proposal_id": str(proposal.id),
            "proposal_version": proposal_version.version_number,
            "document_hash": version.document_hash,
        },
    )
    return contract


def sign_contract(
    *,
    user: User,
    contract_id: uuid.UUID,
    idempotency_key: str,
    expected_document_hash: str,
    signature_provider_reference: str | None,
    ip_metadata: dict[str, object],
    risk_metadata: dict[str, object],
) -> Contract:
    contract = _get_contract_for_update(contract_id)
    if not is_contract_party(user, contract):
        raise ApiError("forbidden", "Forbidden", 403, "Only contract parties may sign")
    if contract.status == "CANCELLED":
        raise ApiError(
            "invalid_state", "Contract cancelled", 409, "A cancelled contract cannot be signed"
        )

    version = _current_contract_version(contract)
    if expected_document_hash != version.document_hash:
        raise ApiError(
            "document_changed",
            "Contract document changed",
            409,
            "The supplied document hash does not match the current contract version",
        )

    key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    prior_for_key = db.session.scalar(
        select(ContractSignature).where(
            ContractSignature.user_id == user.id,
            ContractSignature.idempotency_key_hash == key_hash,
        )
    )
    if prior_for_key is not None:
        if prior_for_key.contract_version_id != version.id:
            raise ApiError(
                "idempotency_key_reused",
                "Idempotency key reused",
                409,
                "The Idempotency-Key was already used for another contract signature",
            )
        return get_contract(contract.id)

    existing = db.session.scalar(
        select(ContractSignature).where(
            ContractSignature.contract_version_id == version.id,
            ContractSignature.user_id == user.id,
        )
    )
    if existing is not None:
        return get_contract(contract.id)

    signature = ContractSignature(
        contract_version_id=version.id,
        user_id=user.id,
        document_hash=version.document_hash,
        ip_metadata=ip_metadata,
        risk_metadata=risk_metadata,
        signature_provider_reference=signature_provider_reference,
        idempotency_key_hash=key_hash,
    )
    db.session.add(signature)
    try:
        db.session.flush()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError(
            "signature_conflict",
            "Signature conflict",
            409,
            "The contract signature was already recorded",
        ) from exc

    record_audit_event(
        action="contract.signed",
        resource_type="contract",
        resource_id=str(contract.id),
        actor_user_id=user.id,
        previous_state=_contract_state(contract, version, signer_has_signature=False),
        new_state=_contract_state(contract, version, signer_has_signature=True),
        metadata={
            "contract_version": version.version_number,
            "document_hash": version.document_hash,
        },
    )

    required_user_ids = {party.user_id for party in contract.parties if party.required_signature}
    signed_user_ids = set(
        db.session.scalars(
            select(ContractSignature.user_id).where(
                ContractSignature.contract_version_id == version.id
            )
        )
    )
    if required_user_ids and required_user_ids <= signed_user_ids:
        previous_state = _contract_state(contract, version)
        contract.status = "ACTIVE"
        contract.activated_at = datetime.now(UTC)
        record_audit_event(
            action="contract.activated",
            resource_type="contract",
            resource_id=str(contract.id),
            actor_user_id=user.id,
            previous_state=previous_state,
            new_state=_contract_state(contract, version),
            metadata={"contract_version": version.version_number},
        )

    db.session.commit()
    return get_contract(contract.id)


def cancel_contract(*, user: User, contract_id: uuid.UUID) -> Contract:
    contract = _get_contract_for_update(contract_id)
    if not can_cancel_contract(user, contract):
        raise ApiError(
            "forbidden", "Forbidden", 403, "Only the employer party may cancel this contract"
        )
    if contract.status == "CANCELLED":
        return get_contract(contract.id)
    version = _current_contract_version(contract)
    if contract.status == "ACTIVE":
        if any(milestone.status != "CREATED" for milestone in version.milestones):
            raise ApiError(
                "invalid_state",
                "Contract work has started",
                409,
                "An active contract cannot be cancelled after milestone work starts",
            )
        from app.payments.models import PaymentIntent

        milestone_ids = [milestone.id for milestone in version.milestones]
        pending_payment = None
        if milestone_ids:
            pending_payment = db.session.scalar(
                select(PaymentIntent.id).where(
                    PaymentIntent.milestone_id.in_(milestone_ids),
                    PaymentIntent.status == "PENDING",
                )
            )
        if pending_payment is not None:
            raise ApiError(
                "invalid_state",
                "Contract has pending funding",
                409,
                "An active contract cannot be cancelled while a funding payment is pending",
            )

    previous_state = _contract_state(contract, version)
    contract.status = "CANCELLED"
    contract.cancelled_at = datetime.now(UTC)
    record_audit_event(
        action="contract.cancelled",
        resource_type="contract",
        resource_id=str(contract.id),
        actor_user_id=user.id,
        previous_state=previous_state,
        new_state=_contract_state(contract, version),
    )
    db.session.commit()
    return get_contract(contract.id)


def _contract_query() -> Select[tuple[Contract]]:
    return select(Contract).options(
        selectinload(Contract.parties),
        selectinload(Contract.versions).selectinload(ContractVersion.signatures),
        selectinload(Contract.versions)
        .selectinload(ContractVersion.milestones)
        .selectinload(Milestone.events),
    )


def _get_contract_for_update(contract_id: uuid.UUID) -> Contract:
    contract = db.session.scalar(
        _contract_query().where(Contract.id == contract_id).with_for_update()
    )
    if contract is None:
        raise ApiError("contract_not_found", "Contract not found", 404, "Contract was not found")
    return contract


def _current_proposal_version(proposal: Proposal) -> ProposalVersion:
    for version in proposal.versions:
        if version.version_number == proposal.current_version:
            return version
    raise RuntimeError("Proposal current_version does not reference a loaded version")


def _current_contract_version(contract: Contract) -> ContractVersion:
    for version in contract.versions:
        if version.version_number == contract.current_version:
            return version
    raise RuntimeError("Contract current_version does not reference a loaded version")


def _contract_state(
    contract: Contract,
    version: ContractVersion,
    *,
    signer_has_signature: bool | None = None,
) -> dict[str, object]:
    state: dict[str, object] = {
        "status": contract.status,
        "current_version": contract.current_version,
        "document_hash": version.document_hash,
    }
    if signer_has_signature is not None:
        state["signer_has_signature"] = signer_has_signature
    return state


def _milestone_terms(proposal_version: ProposalVersion) -> list[tuple[int, str, int, int]]:
    if proposal_version.milestones:
        return [
            (
                milestone.sequence,
                milestone.title,
                milestone.amount_minor,
                milestone.delivery_days,
            )
            for milestone in proposal_version.milestones
        ]
    return [
        (1, "Full contract delivery", proposal_version.amount_minor, proposal_version.delivery_days)
    ]


def _build_snapshot(
    *,
    project: Project,
    proposal: Proposal,
    proposal_version: ProposalVersion,
    milestone_terms: list[tuple[int, str, int, int]],
    attachments: list[ProjectAttachment],
) -> dict[str, object]:
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "source": {
            "project_id": str(project.id),
            "proposal_id": str(proposal.id),
            "proposal_version_id": str(proposal_version.id),
            "proposal_version": proposal_version.version_number,
        },
        "scope": {
            "project_title": project.title,
            "project_description": project.description,
            "proposal_cover_letter": proposal_version.cover_letter,
        },
        "price": {"amount_minor": proposal_version.amount_minor},
        "currency": proposal_version.currency,
        "delivery_days": proposal_version.delivery_days,
        "milestones": [
            {
                "sequence": sequence,
                "title": title,
                "amount_minor": amount_minor,
                "currency": proposal_version.currency,
                "delivery_days": delivery_days,
            }
            for sequence, title, amount_minor, delivery_days in milestone_terms
        ],
        "commission": {"platform_bps": _commission_bps()},
        "refund_terms": None,
        "dispute_terms": None,
        "attachments": [
            {
                "id": str(attachment.id),
                "object_key": attachment.object_key,
                "mime_type": attachment.mime_type,
                "file_size_bytes": attachment.file_size_bytes,
                "scan_status": attachment.scan_status,
            }
            for attachment in attachments
        ],
    }


def _document_hash(snapshot: dict[str, object]) -> str:
    encoded = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _commission_bps() -> int:
    raw = os.getenv("PLATFORM_COMMISSION_BPS", "1000")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("PLATFORM_COMMISSION_BPS must be an integer") from exc
    if value < 0 or value > 10000:
        raise RuntimeError("PLATFORM_COMMISSION_BPS must be between 0 and 10000")
    return value
