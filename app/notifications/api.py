from __future__ import annotations

import uuid
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from app.errors import ApiError
from app.identity.auth import require_access_token
from app.identity.models import User
from app.notifications.service import (
    list_notifications,
    list_preferences,
    mark_notification_read,
    serialize_notification,
    serialize_preference,
    set_preference,
)

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/v1/notifications")


@notifications_bp.get("")
@require_access_token
def notifications():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    after_raw = request.args.get("after")
    try:
        after = datetime.fromisoformat(after_raw) if after_raw else None
        limit = int(request.args.get("limit", "50"))
    except ValueError as exc:
        raise ApiError(
            "validation_error", "Invalid pagination", 422, "Invalid after or limit"
        ) from exc
    return jsonify(
        [
            serialize_notification(item)
            for item in list_notifications(user=user, after=after, limit=limit)
        ]
    )


@notifications_bp.post("/<uuid:notification_id>/read")
@require_access_token
def read_notification(notification_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify(
        serialize_notification(mark_notification_read(user=user, notification_id=notification_id))
    )


@notifications_bp.get("/preferences")
@require_access_token
def preferences():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify([serialize_preference(item) for item in list_preferences(user=user)])


@notifications_bp.put("/preferences")
@require_access_token
def update_preference():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    body = request.get_json(silent=True) or {}
    if not {"event_type", "channel", "enabled"} <= body.keys():
        raise ApiError(
            "validation_error",
            "Invalid preference",
            422,
            "event_type, channel and enabled are required",
        )
    enabled = body["enabled"]
    if not isinstance(enabled, bool):
        raise ApiError("validation_error", "Invalid preference", 422, "enabled must be a boolean")
    preference = set_preference(
        user=user,
        event_type=str(body["event_type"]),
        channel=str(body["channel"]),
        enabled=enabled,
    )
    return jsonify(serialize_preference(preference))
