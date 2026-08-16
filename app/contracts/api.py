from __future__ import annotations

from typing import Any

from flask import Blueprint, g, jsonify, request

from app.common.http import ValidationError, optional_string, parse_uuid, require_string
from app.contracts.models import Contract, ContractVersion
from app.contracts.service import (
    cancel_contract,
    get_contract_for_user,
    get_project_contract_for_user,
    sign_contract,
)
from app.identity.auth import require_roles
from app.identity.models import User
from app.milestones.models import Milestone

contracts_bp = Blueprint("contracts", __name__, url_prefix="/api/v1")


@contracts_bp.get("/projects/<project_id>/contract")
@require_roles("freelancer", "employer")
def get_project_contract(project_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    contract = get_project_contract_for_user(
        user=user, project_id=parse_uuid(project_id, "project_id")
    )
    return jsonify(_serialize_contract(contract))


@contracts_bp.get("/contracts/<contract_id>")
@require_roles("freelancer", "employer")
def get_contract_detail(contract_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    contract = get_contract_for_user(user=user, contract_id=parse_uuid(contract_id, "contract_id"))
    return jsonify(_serialize_contract(contract))


@contracts_bp.post("/contracts/<contract_id>/sign")
@require_roles("freelancer", "employer")
def post_contract_signature(contract_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not idempotency_key:
        raise ValidationError("Idempotency-Key header is required")
    if len(idempotency_key) > 200:
        raise ValidationError("Idempotency-Key must be at most 200 characters")
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object")
    expected_document_hash = require_string(payload, "document_hash", max_length=64).lower()
    if len(expected_document_hash) != 64 or any(
        char not in "0123456789abcdef" for char in expected_document_hash
    ):
        raise ValidationError("document_hash must be a lowercase SHA-256 hex digest")
    provider_reference = optional_string(payload, "signature_provider_reference", max_length=255)
    contract = sign_contract(
        user=user,
        contract_id=parse_uuid(contract_id, "contract_id"),
        idempotency_key=idempotency_key,
        expected_document_hash=expected_document_hash,
        signature_provider_reference=provider_reference,
        ip_metadata={
            "remote_addr": request.remote_addr or "",
            "user_agent": request.user_agent.string[:512],
        },
        risk_metadata={"request_id": str(g.request_id)},
    )
    return jsonify(_serialize_contract(contract))


@contracts_bp.post("/contracts/<contract_id>/cancel")
@require_roles("employer")
def post_contract_cancel(contract_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    contract = cancel_contract(user=user, contract_id=parse_uuid(contract_id, "contract_id"))
    return jsonify(_serialize_contract(contract))


def _serialize_contract(contract: Contract) -> dict[str, object]:
    version = _current_version(contract)
    return {
        "id": str(contract.id),
        "project_id": str(contract.project_id),
        "accepted_proposal_id": str(contract.accepted_proposal_id),
        "employer_user_id": str(contract.employer_user_id),
        "freelancer_user_id": str(contract.freelancer_user_id),
        "status": contract.status,
        "current_version": contract.current_version,
        "created_at": contract.created_at.isoformat(),
        "activated_at": contract.activated_at.isoformat() if contract.activated_at else None,
        "cancelled_at": contract.cancelled_at.isoformat() if contract.cancelled_at else None,
        "parties": [
            {
                "user_id": str(party.user_id),
                "role": party.role,
                "required_signature": party.required_signature,
            }
            for party in sorted(contract.parties, key=lambda item: item.role)
        ],
        "version": _serialize_version(version),
    }


def _serialize_version(version: ContractVersion) -> dict[str, object]:
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "document_hash": version.document_hash,
        "snapshot": version.snapshot,
        "created_at": version.created_at.isoformat(),
        "signatures": [
            {
                "id": str(signature.id),
                "user_id": str(signature.user_id),
                "signed_at": signature.signed_at.isoformat(),
                "document_hash": signature.document_hash,
                "signature_provider_reference": signature.signature_provider_reference,
            }
            for signature in sorted(version.signatures, key=lambda item: str(item.user_id))
        ],
        "milestones": [_serialize_milestone(milestone) for milestone in version.milestones],
    }


def _serialize_milestone(milestone: Milestone) -> dict[str, object]:
    events: list[dict[str, Any]] = [
        {
            "id": str(event.id),
            "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "note": event.note,
            "created_at": event.created_at.isoformat(),
        }
        for event in milestone.events
    ]
    return {
        "id": str(milestone.id),
        "sequence": milestone.sequence,
        "title": milestone.title,
        "amount_minor": milestone.amount_minor,
        "currency": milestone.currency,
        "delivery_days": milestone.delivery_days,
        "status": milestone.status,
        "events": events,
    }


def _current_version(contract: Contract) -> ContractVersion:
    for version in contract.versions:
        if version.version_number == contract.current_version:
            return version
    raise RuntimeError("Contract current_version does not reference a loaded version")
