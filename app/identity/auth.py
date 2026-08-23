from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any

from flask import g, request
from sqlalchemy import select

from app.errors import ApiError
from app.extensions import db
from app.identity.models import User, UserSession
from app.identity.security import decode_token
from app.identity.settings import mfa_step_up_ttl_seconds

View = Callable[..., Any]


def require_access_token(view: View) -> View:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        token = _bearer_token()
        try:
            payload = decode_token(token, expected_type="access")
            user_id = uuid.UUID(str(payload["sub"]))
            session_id = uuid.UUID(str(payload["sid"]))
        except (ValueError, TypeError) as exc:
            raise ApiError("unauthorized", "Unauthorized", 401, "Invalid access token") from exc

        user = db.session.scalar(select(User).where(User.id == user_id))
        session = db.session.scalar(select(UserSession).where(UserSession.id == session_id))
        if (
            user is None
            or not user.is_active
            or session is None
            or session.user_id != user_id
            or session.revoked_at is not None
            or _is_expired(session.expires_at)
        ):
            raise ApiError("unauthorized", "Unauthorized", 401, "User session is unavailable")
        g.current_user = user
        g.current_session_id = session_id
        g.current_session = session
        return view(*args, **kwargs)

    return wrapped


def require_roles(*roles: str) -> Callable[[View], View]:
    def decorator(view: View) -> View:
        @require_access_token
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            user: User = g.current_user
            assigned = {assignment.role for assignment in user.roles}
            if assigned.isdisjoint(roles):
                raise ApiError("forbidden", "Forbidden", 403, "Insufficient permissions")
            if "admin" in roles and "admin" in assigned:
                require_recent_mfa()
            return view(*args, **kwargs)

        return wrapped

    return decorator


def require_recent_mfa() -> None:
    user: User = g.current_user
    session: UserSession = g.current_session
    if user.mfa_enabled_at is None or not user.mfa_seed:
        raise ApiError(
            "mfa_enrollment_required",
            "Multi-factor authentication required",
            403,
            "Enroll multi-factor authentication before this sensitive action",
        )
    verified_at = session.mfa_verified_at
    if verified_at is None:
        raise _mfa_challenge_error()
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)

    ttl = mfa_step_up_ttl_seconds()
    if verified_at + timedelta(seconds=ttl) <= datetime.now(UTC):
        raise _mfa_challenge_error()


def mfa_verified_until(session: UserSession) -> datetime | None:
    if session.mfa_verified_at is None:
        return None
    verified_at = session.mfa_verified_at
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)
    return verified_at + timedelta(seconds=mfa_step_up_ttl_seconds())


def _mfa_challenge_error() -> ApiError:
    return ApiError(
        "mfa_required",
        "Multi-factor authentication required",
        403,
        "Complete multi-factor authentication before this sensitive action",
    )


def _bearer_token() -> str:
    value = request.headers.get("Authorization", "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError("unauthorized", "Unauthorized", 401, "Bearer token is required")
    return token


def _is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)
