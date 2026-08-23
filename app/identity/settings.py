from __future__ import annotations

import os

from flask import current_app


def mfa_secret_key() -> str:
    configured = current_app.config.get("MFA_SECRET_KEY")
    if configured:
        return str(configured)
    environment_value = os.getenv("MFA_SECRET_KEY")
    if environment_value:
        return environment_value
    return str(current_app.config["SECRET_KEY"])


def mfa_step_up_ttl_seconds() -> int:
    return _positive_int("MFA_STEP_UP_TTL_SECONDS", 600)


def auth_max_failed_attempts() -> int:
    return _positive_int("AUTH_MAX_FAILED_ATTEMPTS", 5)


def auth_lock_seconds() -> int:
    return _positive_int("AUTH_LOCK_SECONDS", 900)


def mfa_issuer() -> str:
    configured = current_app.config.get("MFA_ISSUER")
    if configured:
        return str(configured)
    return os.getenv("MFA_ISSUER", "Freelancing Platform")


def _positive_int(name: str, default: int) -> int:
    configured = current_app.config.get(name)
    raw = configured if configured is not None else os.getenv(name, str(default))
    value = int(raw)
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value
