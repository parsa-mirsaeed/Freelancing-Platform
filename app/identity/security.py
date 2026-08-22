from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import current_app

from app.identity.models import User

_password_hasher = PasswordHasher()
REALTIME_TICKET_TTL_SECONDS = 60


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def hash_jti(jti: str) -> str:
    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


def issue_token_pair(user: User, session_id: uuid.UUID) -> tuple[str, str, str, datetime]:
    now = datetime.now(UTC)
    access_ttl = int(current_app.config["ACCESS_TOKEN_TTL_SECONDS"])
    refresh_ttl = int(current_app.config["REFRESH_TOKEN_TTL_SECONDS"])
    roles = [assignment.role for assignment in user.roles]
    refresh_jti = str(uuid.uuid4())
    refresh_expiry = now + timedelta(seconds=refresh_ttl)

    common: dict[str, Any] = {
        "sub": str(user.id),
        "sid": str(session_id),
        "iat": now,
    }
    access = jwt.encode(
        {
            **common,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "roles": roles,
            "exp": now + timedelta(seconds=access_ttl),
        },
        current_app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    refresh = jwt.encode(
        {
            **common,
            "type": "refresh",
            "jti": refresh_jti,
            "exp": refresh_expiry,
        },
        current_app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    return access, refresh, refresh_jti, refresh_expiry


def issue_realtime_ticket(user: User, session_id: uuid.UUID) -> tuple[str, datetime]:
    """Issue a short-lived session-bound token scoped only to realtime connection auth."""
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=REALTIME_TICKET_TTL_SECONDS)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "sid": str(session_id),
            "iat": now,
            "exp": expires_at,
            "jti": str(uuid.uuid4()),
            "type": "realtime",
        },
        current_app.config["SECRET_KEY"],
        algorithm="HS256",
    )
    return token, expires_at


def decode_token(token: str, *, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            current_app.config["SECRET_KEY"],
            algorithms=["HS256"],
            options={"require": ["sub", "sid", "iat", "exp", "jti", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid or expired token") from exc
    if payload.get("type") != expected_type:
        raise ValueError("Unexpected token type")
    return payload
