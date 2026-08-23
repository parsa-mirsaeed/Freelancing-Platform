from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.common.http import require_json_object, require_string
from app.identity.auth import require_access_token, require_recent_mfa
from app.identity.models import User, UserSession
from app.identity.security import issue_realtime_ticket
from app.identity.service import (
    ClientContext,
    client_context,
    confirm_totp_enrollment,
    login_user,
    mfa_status,
    refresh_session,
    register_user,
    revoke_session,
    start_totp_enrollment,
    verify_mfa_challenge,
)

identity_bp = Blueprint("identity", __name__, url_prefix="/api/v1/auth")


@identity_bp.post("/register")
def register():  # type: ignore[no-untyped-def]
    payload = require_json_object(request)
    user, access, refresh = register_user(
        email=require_string(payload, "email"),
        password=require_string(payload, "password"),
        role=require_string(payload, "role"),
        context=_client_context(),
    )
    return jsonify(_token_response(user, access, refresh)), 201


@identity_bp.post("/login")
def login():  # type: ignore[no-untyped-def]
    payload = require_json_object(request)
    user, access, refresh = login_user(
        email=require_string(payload, "email"),
        password=require_string(payload, "password"),
        context=_client_context(),
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
    session: UserSession = g.current_session
    return jsonify(
        {
            "id": str(user.id),
            "email": user.email,
            "roles": [assignment.role for assignment in user.roles],
            "mfa": mfa_status(user=user, session=session),
        }
    )


@identity_bp.get("/mfa")
@require_access_token
def get_mfa_status():  # type: ignore[no-untyped-def]
    return jsonify(mfa_status(user=g.current_user, session=g.current_session))


@identity_bp.post("/mfa/totp/enroll")
@require_access_token
def enroll_mfa():  # type: ignore[no-untyped-def]
    payload = require_json_object(request)
    return jsonify(
        start_totp_enrollment(
            user=g.current_user,
            password=require_string(payload, "password"),
        )
    )


@identity_bp.post("/mfa/totp/confirm")
@require_access_token
def confirm_mfa():  # type: ignore[no-untyped-def]
    payload = require_json_object(request)
    return jsonify(
        confirm_totp_enrollment(
            user=g.current_user,
            session=g.current_session,
            code=require_string(payload, "code", max_length=32),
        )
    )


@identity_bp.post("/mfa/verify")
@require_access_token
def verify_mfa():  # type: ignore[no-untyped-def]
    payload = require_json_object(request)
    return jsonify(
        verify_mfa_challenge(
            user=g.current_user,
            session=g.current_session,
            code=require_string(payload, "code", max_length=64),
        )
    )


@identity_bp.post("/mfa/assert")
@require_access_token
def assert_mfa():  # type: ignore[no-untyped-def]
    require_recent_mfa()
    return "", 204


def _token_response(user: User, access: str, refresh: str) -> dict[str, object]:
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "roles": [assignment.role for assignment in user.roles],
            "mfa_enabled": user.mfa_enabled_at is not None,
        },
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
    }


def _client_context() -> ClientContext:
    return client_context(
        remote_addr=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
        device_id=request.headers.get("X-Device-ID"),
    )
