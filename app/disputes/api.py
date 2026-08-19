from __future__ import annotations

import uuid

from flask import Blueprint, g, jsonify, request

from app.disputes.service import (
    add_evidence,
    admin_transition,
    get_dispute_for_user,
    open_dispute,
    resolve_dispute,
    serialize_dispute,
)
from app.errors import ApiError
from app.identity.auth import require_access_token, require_roles
from app.identity.models import User

disputes_bp = Blueprint("disputes", __name__, url_prefix="/api/v1")


@disputes_bp.post("/milestones/<uuid:milestone_id>/disputes")
@require_access_token
def create_dispute(milestone_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    body = _body()
    dispute = open_dispute(
        user=user,
        milestone_id=milestone_id,
        reason=_required_string(body, "reason"),
    )
    return jsonify(serialize_dispute(dispute)), 201


@disputes_bp.get("/disputes/<uuid:dispute_id>")
@require_access_token
def get_dispute(dispute_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify(serialize_dispute(get_dispute_for_user(user=user, dispute_id=dispute_id)))


@disputes_bp.post("/disputes/<uuid:dispute_id>/evidence")
@require_access_token
def create_evidence(dispute_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    body = _body()
    raw_file_id = body.get("file_id")
    if raw_file_id is None:
        raise ApiError("validation_error", "File required", 422, "file_id is required")
    try:
        file_id = uuid.UUID(str(raw_file_id))
    except ValueError as exc:
        raise ApiError("validation_error", "Invalid file", 422, "file_id must be a UUID") from exc
    note = body.get("note", "")
    if not isinstance(note, str):
        raise ApiError("validation_error", "Invalid note", 422, "note must be a string")
    evidence = add_evidence(
        user=user,
        dispute_id=dispute_id,
        file_id=file_id,
        note=note,
    )
    return (
        jsonify(
            {
                "id": str(evidence.id),
                "dispute_id": str(evidence.dispute_id),
                "file_id": str(evidence.file_id),
                "submitted_by_user_id": str(evidence.submitted_by_user_id),
                "note": evidence.note,
                "created_at": evidence.created_at.isoformat(),
            }
        ),
        201,
    )


@disputes_bp.post("/disputes/<uuid:dispute_id>/transitions")
@require_roles("admin")
def transition_dispute(dispute_id: uuid.UUID):  # type: ignore[no-untyped-def]
    administrator: User = g.current_user
    body = _body()
    dispute = admin_transition(
        administrator=administrator,
        dispute_id=dispute_id,
        to_status=_required_string(body, "to_status"),
        reason=_required_string(body, "reason"),
    )
    return jsonify(serialize_dispute(dispute))


@disputes_bp.post("/disputes/<uuid:dispute_id>/resolve")
@require_roles("admin")
def resolve(dispute_id: uuid.UUID):  # type: ignore[no-untyped-def]
    administrator: User = g.current_user
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not idempotency_key:
        raise ApiError(
            "idempotency_key_required",
            "Idempotency key required",
            400,
            "Idempotency-Key is required for dispute resolution",
        )
    body = _body()
    response, status = resolve_dispute(
        administrator=administrator,
        dispute_id=dispute_id,
        outcome=_required_string(body, "outcome"),
        reason=_required_string(body, "reason"),
        freelancer_award_minor=_optional_minor(body, "freelancer_award_minor"),
        client_refund_minor=_optional_minor(body, "client_refund_minor"),
        idempotency_key=idempotency_key,
    )
    return jsonify(response), status


def _body() -> dict[str, object]:
    body = request.get_json(silent=True)
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ApiError(
            "validation_error",
            "Invalid request",
            422,
            "Request body must be a JSON object",
        )
    return body


def _required_string(body: dict[str, object], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str):
        raise ApiError(
            "validation_error",
            f"{key} required",
            422,
            f"{key} must be a string",
        )
    return value


def _optional_minor(body: dict[str, object], key: str) -> int | None:
    value = body.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(
            "validation_error",
            "Invalid amount",
            422,
            f"{key} must be an integer",
        )
    return value
