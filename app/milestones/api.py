from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.common.http import (
    ValidationError,
    optional_string,
    parse_uuid,
    require_json_object,
    require_string,
)
from app.identity.auth import require_roles
from app.identity.models import User
from app.milestones.models import Milestone
from app.milestones.service import (
    approve_milestone,
    get_milestone_for_user,
    request_milestone_changes,
    start_milestone,
    submit_milestone,
)

milestones_bp = Blueprint("milestones", __name__, url_prefix="/api/v1")


@milestones_bp.get("/milestones/<milestone_id>")
@require_roles("freelancer", "employer")
def get_milestone_detail(milestone_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    milestone = get_milestone_for_user(
        user=user, milestone_id=parse_uuid(milestone_id, "milestone_id")
    )
    return jsonify(_serialize_milestone(milestone))


@milestones_bp.post("/milestones/<milestone_id>/start")
@require_roles("freelancer")
def post_milestone_start(milestone_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    milestone = start_milestone(user=user, milestone_id=parse_uuid(milestone_id, "milestone_id"))
    return jsonify(_serialize_milestone(milestone))


@milestones_bp.post("/milestones/<milestone_id>/submit")
@require_roles("freelancer")
def post_milestone_submit(milestone_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object")
    note = optional_string(payload, "note", max_length=4000) or ""
    milestone = submit_milestone(
        user=user,
        milestone_id=parse_uuid(milestone_id, "milestone_id"),
        note=note,
    )
    return jsonify(_serialize_milestone(milestone))


@milestones_bp.post("/milestones/<milestone_id>/request-changes")
@require_roles("employer")
def post_milestone_request_changes(milestone_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    milestone = request_milestone_changes(
        user=user,
        milestone_id=parse_uuid(milestone_id, "milestone_id"),
        note=require_string(payload, "note", max_length=4000),
    )
    return jsonify(_serialize_milestone(milestone))


@milestones_bp.post("/milestones/<milestone_id>/approve")
@require_roles("employer")
def post_milestone_approve(milestone_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    milestone = approve_milestone(user=user, milestone_id=parse_uuid(milestone_id, "milestone_id"))
    return jsonify(_serialize_milestone(milestone))


def _serialize_milestone(milestone: Milestone) -> dict[str, object]:
    return {
        "id": str(milestone.id),
        "contract_version_id": str(milestone.contract_version_id),
        "sequence": milestone.sequence,
        "title": milestone.title,
        "amount_minor": milestone.amount_minor,
        "currency": milestone.currency,
        "delivery_days": milestone.delivery_days,
        "status": milestone.status,
        "events": [
            {
                "id": str(event.id),
                "actor_user_id": str(event.actor_user_id) if event.actor_user_id else None,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "note": event.note,
                "created_at": event.created_at.isoformat(),
            }
            for event in milestone.events
        ],
    }
