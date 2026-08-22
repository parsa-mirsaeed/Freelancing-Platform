from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.common.http import require_json_object, require_string
from app.identity.auth import require_access_token
from app.identity.models import User
from app.identity.security import issue_realtime_ticket
from app.identity.service import login_user, refresh_session, register_user, revoke_session

identity_bp = Blueprint("identity", __name__, url_prefix="/api/v1/auth")


@identity_bp.post("/register")
def register():  # type: ignore[no-untyped-def]
    payload = require_json_object(request)
    user, access, refresh = register_user(
        email=require_string(payload, "email"),
        password=require_string(payload, "password"),
        role=require_string(payload, "role"),
    )
    return jsonify(_token_response(user, access, refresh)), 201


@identity_bp.post("/login")
def login():  # type: ignore[no-untyped-def]
    payload = require_json_object(request)
    user, access, refresh = login_user(
        email=require_string(payload, "email"),
        password=require_string(payload, "password"),
    )
    return jsonify(_token_response(user, access, refresh))


@identity_bp.post("/refresh")
def refresh():  # type: ignore[no-untyped-def]
    payload = require_json_object(request)
    access, refresh_token = refresh_session(require_string(payload, "refresh_token"))
    return jsonify({"access_token": access, "refresh_token": refresh_token, "token_type": "Bearer"})


@identity_bp.post("/realtime-ticket")
@require_access_token
def realtime_ticket():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    token, expires_at = issue_realtime_ticket(user, g.current_session_id)
    return jsonify(
        {
            "token": token,
            "token_type": "Realtime",
            "expires_at": expires_at.isoformat(),
        }
    )


@identity_bp.post("/logout")
@require_access_token
def logout():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    revoke_session(session_id=g.current_session_id, actor_user_id=user.id)
    return "", 204


@identity_bp.get("/me")
@require_access_token
def me():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify(
        {
            "id": str(user.id),
            "email": user.email,
            "roles": [assignment.role for assignment in user.roles],
        }
    )


def _token_response(user: User, access: str, refresh: str) -> dict[str, object]:
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "roles": [assignment.role for assignment in user.roles],
        },
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
    }
