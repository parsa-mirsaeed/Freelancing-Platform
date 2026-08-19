from __future__ import annotations

import uuid

from flask import Blueprint, g, jsonify, request

from app.errors import ApiError
from app.fraud.service import assess_risk, review_assessment, serialize_assessment
from app.identity.auth import require_roles
from app.identity.models import User

fraud_bp = Blueprint("fraud", __name__)


@fraud_bp.post("/api/v1/admin/risk/assessments")
@require_roles("admin")
def create_assessment():  # type: ignore[no-untyped-def]
    administrator: User = g.current_user
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("validation_error", "Invalid JSON", 422, "JSON object body is required")
    try:
        subject_user_id = uuid.UUID(str(body["subject_user_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            "validation_error",
            "Invalid subject user id",
            422,
            "subject_user_id must be a UUID",
        ) from exc
    text = body.get("text", "")
    if not isinstance(text, str):
        raise ApiError("validation_error", "Invalid text", 422, "text must be a string")
    assessment = assess_risk(
        administrator=administrator,
        subject_user_id=subject_user_id,
        text=text,
    )
    return jsonify(serialize_assessment(assessment)), 201


@fraud_bp.post("/api/v1/admin/risk/assessments/<uuid:assessment_id>/review")
@require_roles("admin")
def review(assessment_id: uuid.UUID):  # type: ignore[no-untyped-def]
    administrator: User = g.current_user
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("validation_error", "Invalid JSON", 422, "JSON object body is required")
    decision = body.get("decision")
    note = body.get("note", "")
    if not isinstance(decision, str) or not isinstance(note, str):
        raise ApiError(
            "validation_error",
            "Invalid review payload",
            422,
            "decision and note must be strings",
        )
    assessment = review_assessment(
        administrator=administrator,
        assessment_id=assessment_id,
        decision=decision,
        note=note,
    )
    return jsonify(serialize_assessment(assessment))
