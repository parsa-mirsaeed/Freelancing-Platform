from __future__ import annotations

import uuid

from flask import Blueprint, g, jsonify, request

from app.errors import ApiError
from app.identity.auth import require_roles
from app.identity.models import User
from app.recommendations.pricing import estimate_project_price
from app.recommendations.registry import list_models
from app.recommendations.service import (
    recommend_for_project,
    record_client_event,
    serialize_model,
)
from app.recommendations.skills import suggest_skills

recommendations_bp = Blueprint("recommendations", __name__)


@recommendations_bp.get("/api/v1/projects/<uuid:project_id>/recommendations")
@require_roles("employer")
def recommendations(project_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    try:
        limit = int(request.args.get("limit", "10"))
    except ValueError as exc:
        raise ApiError(
            "validation_error",
            "Invalid limit",
            422,
            "limit must be an integer",
        ) from exc
    if limit < 1 or limit > 20:
        raise ApiError(
            "validation_error",
            "Invalid limit",
            422,
            "limit must be between 1 and 20",
        )
    return jsonify(recommend_for_project(user=user, project_id=project_id, limit=limit))


@recommendations_bp.post("/api/v1/recommendations/<uuid:run_id>/events")
@require_roles("employer")
def recommendation_event(run_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("validation_error", "Invalid JSON", 422, "JSON object body is required")
    try:
        freelancer_user_id = uuid.UUID(str(body["freelancer_user_id"]))
        event_type = str(body["event_type"])
        client_event_id = str(body["client_event_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ApiError(
            "validation_error",
            "Invalid recommendation event",
            422,
            "freelancer_user_id, event_type, and client_event_id are required",
        ) from exc
    event, created = record_client_event(
        user=user,
        run_id=run_id,
        freelancer_user_id=freelancer_user_id,
        event_type=event_type,
        client_event_id=client_event_id,
    )
    return (
        jsonify(
            {
                "id": str(event.id),
                "run_id": str(event.run_id),
                "freelancer_user_id": str(event.freelancer_user_id),
                "event_type": event.event_type,
                "created": created,
            }
        ),
        201 if created else 200,
    )


@recommendations_bp.get("/api/v1/freelancers/me/ai/skill-suggestions")
@require_roles("freelancer")
def skill_suggestions():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify(suggest_skills(user=user))


@recommendations_bp.get("/api/v1/projects/<uuid:project_id>/ai/price-estimate")
@require_roles("employer")
def price_estimate(project_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify(estimate_project_price(user=user, project_id=project_id))


@recommendations_bp.get("/api/v1/admin/ml/models")
@require_roles("admin")
def model_registry():  # type: ignore[no-untyped-def]
    return jsonify({"items": [serialize_model(model) for model in list_models()]})
