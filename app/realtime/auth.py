from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.extensions import db
from app.identity.models import User, UserSession
from app.identity.security import decode_token


@dataclass(frozen=True, slots=True)
class SocketPrincipal:
    user: User
    session_id: uuid.UUID
    access_expires_at: datetime


def authenticate_socket_token(token: str) -> SocketPrincipal | None:
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(str(payload["sub"]))
        session_id = uuid.UUID(str(payload["sid"]))
        access_expires_at = datetime.fromtimestamp(float(payload["exp"]), tz=UTC)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    user = db.session.scalar(select(User).where(User.id == user_id))
    session = db.session.scalar(select(UserSession).where(UserSession.id == session_id))
    if user is None or session is None or not user.is_active or session.user_id != user.id:
        return None
    session_expires_at = session.expires_at
    if session_expires_at.tzinfo is None:
        session_expires_at = session_expires_at.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    if session.revoked_at is not None or session_expires_at <= now or access_expires_at <= now:
        return None
    return SocketPrincipal(
        user=user,
        session_id=session_id,
        access_expires_at=access_expires_at,
    )


def load_socket_user(*, user_id: uuid.UUID, session_id: uuid.UUID) -> User | None:
    user = db.session.scalar(select(User).where(User.id == user_id))
    session = db.session.scalar(select(UserSession).where(UserSession.id == session_id))
    if user is None or session is None or not user.is_active or session.user_id != user.id:
        return None
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if session.revoked_at is not None or expires_at <= datetime.now(UTC):
        return None
    return user
