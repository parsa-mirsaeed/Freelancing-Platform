from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit.service import record_audit_event
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User, UserRole, UserSession
from app.identity.security import (
    decode_token,
    hash_jti,
    hash_password,
    issue_token_pair,
    verify_password,
)

ALLOWED_SELF_SERVICE_ROLES = {"freelancer", "employer"}


def register_user(*, email: str, password: str, role: str) -> tuple[User, str, str]:
    normalized_email = _normalize_email(email)
    if role not in ALLOWED_SELF_SERVICE_ROLES:
        raise ApiError(
            "validation_error", "Invalid role", 422, "Role must be freelancer or employer"
        )
    if db.session.scalar(select(User.id).where(User.email == normalized_email)) is not None:
        raise ApiError(
            "email_in_use", "Email unavailable", 409, "An account already uses this email"
        )

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        raise ApiError("validation_error", "Invalid password", 422, str(exc)) from exc

    user = User(email=normalized_email, password_hash=password_hash)
    user.roles.append(UserRole(role=role))
    db.session.add(user)
    try:
        db.session.flush()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError(
            "email_in_use", "Email unavailable", 409, "An account already uses this email"
        ) from exc
    access, refresh = _create_session(user)
    record_audit_event(
        action="identity.user_registered",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
        metadata={"initial_role": role},
    )
    db.session.commit()
    return user, access, refresh


def login_user(*, email: str, password: str) -> tuple[User, str, str]:
    user = db.session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        raise ApiError(
            "invalid_credentials", "Invalid credentials", 401, "Email or password is incorrect"
        )
    access, refresh = _create_session(user)
    record_audit_event(
        action="identity.login_succeeded",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
    )
    db.session.commit()
    return user, access, refresh


def refresh_session(refresh_token: str) -> tuple[str, str]:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
        session_id = uuid.UUID(str(payload["sid"]))
        user_id = uuid.UUID(str(payload["sub"]))
    except (ValueError, TypeError) as exc:
        raise ApiError("unauthorized", "Unauthorized", 401, "Invalid refresh token") from exc

    session = db.session.scalar(select(UserSession).where(UserSession.id == session_id))
    now = datetime.now(UTC)
    if (
        session is None
        or session.user_id != user_id
        or session.revoked_at is not None
        or _normalized_datetime(session.expires_at) <= now
        or session.refresh_jti_hash != hash_jti(str(payload["jti"]))
    ):
        raise ApiError("unauthorized", "Unauthorized", 401, "Refresh session is unavailable")

    access, refresh, refresh_jti, refresh_expiry = issue_token_pair(session.user, session.id)
    session.refresh_jti_hash = hash_jti(refresh_jti)
    session.expires_at = refresh_expiry
    record_audit_event(
        action="identity.session_refreshed",
        resource_type="session",
        resource_id=str(session.id),
        actor_user_id=user_id,
    )
    db.session.commit()
    return access, refresh


def revoke_session(*, session_id: uuid.UUID, actor_user_id: uuid.UUID) -> None:
    session = db.session.scalar(select(UserSession).where(UserSession.id == session_id))
    if session is None or session.user_id != actor_user_id:
        return
    if session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        record_audit_event(
            action="identity.session_revoked",
            resource_type="session",
            resource_id=str(session.id),
            actor_user_id=actor_user_id,
        )
        db.session.commit()


def _create_session(user: User) -> tuple[str, str]:
    session_id = uuid.uuid4()
    access, refresh, refresh_jti, refresh_expiry = issue_token_pair(user, session_id)
    db.session.add(
        UserSession(
            id=session_id,
            user_id=user.id,
            refresh_jti_hash=hash_jti(refresh_jti),
            expires_at=refresh_expiry,
        )
    )
    return access, refresh


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if (
        len(normalized) > 320
        or normalized.count("@") != 1
        or " " in normalized
        or normalized.startswith("@")
        or normalized.endswith("@")
    ):
        raise ApiError(
            "validation_error", "Invalid email", 422, "A valid email address is required"
        )
    local, domain = normalized.rsplit("@", 1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ApiError(
            "validation_error", "Invalid email", 422, "A valid email address is required"
        )
    return normalized


def _normalized_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
