from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import uuid
from datetime import UTC, datetime
from urllib.parse import quote

from app.identity.models import User
from app.identity.settings import mfa_issuer, mfa_secret_key

TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6
TOTP_WINDOW = 1
RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_BYTES = 6


def new_mfa_seed() -> str:
    return secrets.token_hex(16)


def totp_secret(user: User) -> str:
    if not user.mfa_seed:
        raise ValueError("MFA enrollment has not started")
    digest = hmac.new(
        mfa_secret_key().encode("utf-8"),
        f"totp:{user.id}:{user.mfa_seed}".encode(),
        hashlib.sha256,
    ).digest()[:20]
    return base64.b32encode(digest).decode("ascii").rstrip("=")


def provisioning_uri(user: User) -> str:
    secret = totp_secret(user)
    issuer = mfa_issuer()
    label = quote(f"{issuer}:{user.email}", safe="")
    issuer_param = quote(issuer, safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={issuer_param}"
        f"&period={TOTP_PERIOD_SECONDS}&digits={TOTP_DIGITS}&algorithm=SHA1"
    )


def verify_totp(user: User, code: str, *, now: datetime | None = None) -> bool:
    normalized = code.strip().replace(" ", "")
    if len(normalized) != TOTP_DIGITS or not normalized.isdigit():
        return False
    moment = now or datetime.now(UTC)
    counter = int(moment.timestamp()) // TOTP_PERIOD_SECONDS
    secret = totp_secret(user)
    return any(
        hmac.compare_digest(normalized, totp_code_for_secret(secret, counter + offset))
        for offset in range(-TOTP_WINDOW, TOTP_WINDOW + 1)
    )


def totp_code_for_secret(secret: str, counter: int | None = None) -> str:
    if counter is None:
        counter = int(datetime.now(UTC).timestamp()) // TOTP_PERIOD_SECONDS
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def generate_recovery_codes() -> list[str]:
    return [secrets.token_hex(RECOVERY_CODE_BYTES).upper() for _ in range(RECOVERY_CODE_COUNT)]


def hash_recovery_code(user_id: uuid.UUID, code: str) -> str:
    normalized = code.strip().replace("-", "").replace(" ", "").upper()
    return hmac.new(
        mfa_secret_key().encode("utf-8"),
        f"recovery:{user_id}:{normalized}".encode(),
        hashlib.sha256,
    ).hexdigest()
