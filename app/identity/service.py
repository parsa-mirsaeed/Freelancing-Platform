from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.audit.service import record_audit_event
from app.errors import ApiError
from app.extensions import db
from app.identity.auth import mfa_verified_until
from app.identity.mfa import (
    generate_recovery_codes,
    hash_recovery_code,
    new_mfa_seed,
    provisioning_uri,
    totp_secret,
    verify_totp,
)
from app.identity.models import User, UserDevice, UserRole, UserSession, UserVerification
from app.identity.pii import current_pii_cipher
from app.identity.security import (
    decode_token,
    hash_jti,
    hash_password,
    issue_token_pair,
    verify_password,
)
from app.identity.settings import auth_lock_seconds, auth_max_failed_attempts

ALLOWED_SELF_SERVICE_ROLES = {"freelancer", "employer"}
MFA_RECOVERY_KIND = "mfa_recovery"
_EMAIL_CONTEXT = "user.email"
_DUMMY_PASSWORD_HASH: str | None = None


@dataclass(frozen=True, slots=True)
class ClientContext:
    ip_hash: str | None
    user_agent_hash: str
    fingerprint_hash: str


def client_context(
    *, remote_addr: str | None, user_agent: str, device_id: str | None
) -> ClientContext:
    ip_hash = _hash_optional(remote_addr)
    user_agent_hash = hashlib.sha256(user_agent.encode()).hexdigest()
    stable_device = (device_id or "").strip()[:200]
    fingerprint_material = f"{stable_device}\0{user_agent}"
    return ClientContext(
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
        fingerprint_hash=hashlib.sha256(fingerprint_material.encode()).hexdigest(),
    )


def register_user(
    *, email: str, password: str, role: str, context: ClientContext | None = None
) -> tuple[User, str, str]:
    normalized_email = _normalize_email(email)
    if role not in ALLOWED_SELF_SERVICE_ROLES:
        raise ApiError(
            "validation_error", "Invalid role", 422, "Role must be freelancer or employer"
        )
    lookup_hash = _email_lookup_hash(normalized_email)
    if db.session.scalar(select(User.id).where(User.email_lookup_hash == lookup_hash)) is not None:
        raise ApiError(
            "email_in_use", "Email unavailable", 409, "An account already uses this email"
        )

    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        raise ApiError("validation_error", "Invalid password", 422, str(exc)) from exc

    user = User(password_hash=password_hash)
    user.email = normalized_email
    user.roles.append(UserRole(role=role))
    db.session.add(user)
    try:
        db.session.flush()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError(
            "email_in_use", "Email unavailable", 409, "An account already uses this email"
        ) from exc
    access, refresh, _ = _create_session(user, context)
    record_audit_event(
        action="identity.user_registered",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
        metadata={"initial_role": role},
    )
    db.session.commit()
    return user, access, refresh


def login_user(
    *, email: str, password: str, context: ClientContext | None = None
) -> tuple[User, str, str]:
    normalized_email = email.strip().lower()
    user = db.session.scalar(
        select(User)
        .where(User.email_lookup_hash == _email_lookup_hash(normalized_email))
        .with_for_update()
    )
    password_ok = verify_password(
        user.password_hash if user is not None else _dummy_password_hash(), password
    )
    now = datetime.now(UTC)
    if user is None or not user.is_active:
        raise _invalid_credentials()

    if user.locked_until is not None and _normalized_datetime(user.locked_until) > now:
        _record_login_risk(user, context, reason="temporary_lock")
        db.session.commit()
        raise _invalid_credentials()

    if not password_ok:
        user.failed_login_attempts += 1
        locked = user.failed_login_attempts >= auth_max_failed_attempts()
        if locked:
            user.locked_until = now + timedelta(seconds=auth_lock_seconds())
            user.failed_login_attempts = 0
        _record_login_risk(user, context, reason="temporary_lock" if locked else "invalid_password")
        db.session.commit()
        raise _invalid_credentials()

    user.failed_login_attempts = 0
    user.locked_until = None
    pii_key_rotated = user.rotate_email_encryption_if_needed()
    access, refresh, new_device = _create_session(user, context)
    record_audit_event(
        action="identity.login_succeeded",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
        metadata={"new_device": new_device, "pii_key_rotated": pii_key_rotated},
    )
    if new_device:
        _record_login_risk(user, context, reason="new_device")
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
    session.last_seen_at = now
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


def start_totp_enrollment(*, user: User, password: str) -> dict[str, str]:
    if not verify_password(user.password_hash, password):
        raise ApiError(
            "invalid_credentials",
            "Invalid credentials",
            401,
            "Current password is incorrect",
        )
    if user.mfa_enabled_at is not None:
        raise ApiError("mfa_already_enabled", "MFA already enabled", 409, "MFA is already enabled")
    if not user.mfa_seed:
        user.mfa_seed = new_mfa_seed()
        record_audit_event(
            action="identity.mfa_enrollment_started",
            resource_type="user",
            resource_id=str(user.id),
            actor_user_id=user.id,
        )
        db.session.commit()
    return {"secret": totp_secret(user), "otpauth_uri": provisioning_uri(user)}


def confirm_totp_enrollment(*, user: User, session: UserSession, code: str) -> dict[str, object]:
    if user.mfa_enabled_at is not None:
        raise ApiError("mfa_already_enabled", "MFA already enabled", 409, "MFA is already enabled")
    if not user.mfa_seed:
        raise ApiError(
            "mfa_enrollment_required",
            "MFA enrollment required",
            409,
            "Start MFA enrollment before confirming it",
        )
    if not verify_totp(user, code):
        raise ApiError("invalid_mfa_code", "Invalid MFA code", 422, "The MFA code is invalid")

    now = datetime.now(UTC)
    user.mfa_enabled_at = now
    session.mfa_verified_at = now
    db.session.execute(
        delete(UserVerification).where(
            UserVerification.user_id == user.id,
            UserVerification.kind == MFA_RECOVERY_KIND,
        )
    )
    recovery_codes = generate_recovery_codes()
    for recovery_code in recovery_codes:
        db.session.add(
            UserVerification(
                user_id=user.id,
                kind=MFA_RECOVERY_KIND,
                token_hash=hash_recovery_code(user.id, recovery_code),
            )
        )
    record_audit_event(
        action="identity.mfa_enabled",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
    )
    db.session.commit()
    return {
        "recovery_codes": recovery_codes,
        "verified_until": _iso_or_none(mfa_verified_until(session)),
    }


def verify_mfa_challenge(*, user: User, session: UserSession, code: str) -> dict[str, object]:
    if user.mfa_enabled_at is None or not user.mfa_seed:
        raise ApiError(
            "mfa_enrollment_required",
            "MFA enrollment required",
            403,
            "Enroll MFA before attempting a challenge",
        )

    now = datetime.now(UTC)
    recovery_used = False
    if not verify_totp(user, code, now=now):
        recovery_hash = hash_recovery_code(user.id, code)
        recovery = db.session.scalar(
            select(UserVerification)
            .where(
                UserVerification.user_id == user.id,
                UserVerification.kind == MFA_RECOVERY_KIND,
                UserVerification.token_hash == recovery_hash,
                UserVerification.consumed_at.is_(None),
            )
            .with_for_update()
        )
        if recovery is None:
            record_audit_event(
                action="identity.mfa_challenge_failed",
                resource_type="session",
                resource_id=str(session.id),
                actor_user_id=user.id,
            )
            db.session.commit()
            raise ApiError("invalid_mfa_code", "Invalid MFA code", 401, "The MFA code is invalid")
        recovery.consumed_at = now
        recovery_used = True

    session.mfa_verified_at = now
    record_audit_event(
        action="identity.mfa_verified",
        resource_type="session",
        resource_id=str(session.id),
        actor_user_id=user.id,
        metadata={"recovery_code": recovery_used},
    )
    if recovery_used:
        record_audit_event(
            action="identity.mfa_recovery_code_used",
            resource_type="user",
            resource_id=str(user.id),
            actor_user_id=user.id,
        )
    db.session.commit()
    return {
        "verified_until": _iso_or_none(mfa_verified_until(session)),
        "recovery_code_used": recovery_used,
    }


def mfa_status(*, user: User, session: UserSession) -> dict[str, object]:
    remaining = 0
    if user.mfa_enabled_at is not None:
        remaining = int(
            db.session.scalar(
                select(func.count(UserVerification.id)).where(
                    UserVerification.user_id == user.id,
                    UserVerification.kind == MFA_RECOVERY_KIND,
                    UserVerification.consumed_at.is_(None),
                )
            )
            or 0
        )
    verified_until = mfa_verified_until(session)
    now = datetime.now(UTC)
    if verified_until is not None and _normalized_datetime(verified_until) <= now:
        verified_until = None
    return {
        "enabled": user.mfa_enabled_at is not None,
        "verified_until": _iso_or_none(verified_until),
        "recovery_codes_remaining": remaining,
    }


def _create_session(user: User, context: ClientContext | None) -> tuple[str, str, bool]:
    session_id = uuid.uuid4()
    access, refresh, refresh_jti, refresh_expiry = issue_token_pair(user, session_id)
    device: UserDevice | None = None
    new_device = False
    if context is not None:
        device = db.session.scalar(
            select(UserDevice).where(
                UserDevice.user_id == user.id,
                UserDevice.fingerprint_hash == context.fingerprint_hash,
            )
        )
        now = datetime.now(UTC)
        if device is None:
            device = UserDevice(
                user_id=user.id,
                fingerprint_hash=context.fingerprint_hash,
                user_agent_hash=context.user_agent_hash,
                first_seen_at=now,
                last_seen_at=now,
            )
            db.session.add(device)
            db.session.flush()
            new_device = True
        else:
            device.last_seen_at = now
    db.session.add(
        UserSession(
            id=session_id,
            user_id=user.id,
            device_id=device.id if device is not None else None,
            refresh_jti_hash=hash_jti(refresh_jti),
            ip_hash=context.ip_hash if context is not None else None,
            user_agent_hash=context.user_agent_hash if context is not None else None,
            expires_at=refresh_expiry,
        )
    )
    return access, refresh, new_device


def _record_login_risk(user: User, context: ClientContext | None, *, reason: str) -> None:
    record_audit_event(
        action="identity.login_risk",
        resource_type="user",
        resource_id=str(user.id),
        actor_user_id=user.id,
        metadata={
            "reason": reason,
            "ip_hash": context.ip_hash if context else None,
            "device_fingerprint_hash": context.fingerprint_hash if context else None,
        },
    )


def _invalid_credentials() -> ApiError:
    return ApiError(
        "invalid_credentials", "Invalid credentials", 401, "Email or password is incorrect"
    )


def _dummy_password_hash() -> str:
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        _DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-anti-enumeration")
    return _DUMMY_PASSWORD_HASH


def _hash_optional(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode()).hexdigest()


def _email_lookup_hash(normalized_email: str) -> str:
    return current_pii_cipher().blind_index(normalized_email, context=_EMAIL_CONTEXT)


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


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
