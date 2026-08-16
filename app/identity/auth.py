from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any

from flask import g, request
from sqlalchemy import select

from app.errors import ApiError
from app.extensions import db
from app.identity.models import User, UserSession
from app.identity.security import decode_token

View = Callable[..., Any]


def require_access_token(view: View) -> View:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        token = _bearer_token()
        try:
            payload = decode_token(token, expected_type="access")
            user_id = uuid.UUID(str(payload["sub"]))
        except (ValueError, TypeError) as exc:
            raise ApiError("unauthorized", "Unauthorized", 401, "Invalid access token") from exc

        session_id = uuid.UUID(str(payload["sid"]))
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
            return view(*args, **kwargs)

        return wrapped

    return decorator


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
