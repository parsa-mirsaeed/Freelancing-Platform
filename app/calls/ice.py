from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from flask import current_app

from app.errors import ApiError
from app.observability import increment_counter

_DEFAULT_STUN_URLS = "stun:localhost:3478"
_DEFAULT_TURN_URLS = "turn:localhost:3478?transport=udp,turn:localhost:3478?transport=tcp"
_DEFAULT_TURN_SECRET = "-".join(("development", "only", "turn", "secret"))
_DEFAULT_TTL_SECONDS = 600
_MIN_TTL_SECONDS = 60
_MAX_TTL_SECONDS = 3600


def issue_ice_servers(
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    now: int | None = None,
) -> dict[str, Any]:
    ttl_seconds = _ttl_seconds()
    stun_urls = _urls(_setting("STUN_URLS", _DEFAULT_STUN_URLS))
    turn_urls = _urls(_setting("TURN_URLS", _DEFAULT_TURN_URLS))
    turn_secret = _setting("TURN_SHARED_SECRET", _DEFAULT_TURN_SECRET)
    environment = str(current_app.config.get("APP_ENV", "development"))

    if environment == "production" and (
        not turn_urls or not turn_secret or turn_secret == _DEFAULT_TURN_SECRET
    ):
        raise ApiError(
            "turn_not_configured",
            "TURN is not configured",
            503,
            "Production requires TURN_URLS and a non-default TURN_SHARED_SECRET",
        )

    issued_at = int(time.time()) if now is None else int(now)
    expires_unix = issued_at + ttl_seconds
    username = f"{expires_unix}:{user_id}:{session_id}"
    # coturn's TURN REST API uses HMAC-SHA1 for ephemeral credentials.
    digest = hmac.new(turn_secret.encode(), username.encode(), hashlib.sha1).digest()
    credential = base64.b64encode(digest).decode("ascii")

    ice_servers: list[dict[str, Any]] = []
    if stun_urls:
        ice_servers.append({"urls": stun_urls})
    if turn_urls:
        ice_servers.append(
            {
                "urls": turn_urls,
                "username": username,
                "credential": credential,
            }
        )
        increment_counter("turn_credentials_issued_total")
    return {
        "ice_servers": ice_servers,
        "expires_at": datetime.fromtimestamp(expires_unix, tz=UTC).isoformat(),
        "ttl_seconds": ttl_seconds,
    }


def _ttl_seconds() -> int:
    raw = _setting("TURN_CREDENTIAL_TTL_SECONDS", str(_DEFAULT_TTL_SECONDS))
    try:
        ttl = int(raw)
    except ValueError as exc:
        raise ApiError(
            "turn_configuration_error",
            "Invalid TURN configuration",
            503,
            "TURN_CREDENTIAL_TTL_SECONDS must be an integer",
        ) from exc
    if ttl < _MIN_TTL_SECONDS or ttl > _MAX_TTL_SECONDS:
        raise ApiError(
            "turn_configuration_error",
            "Invalid TURN configuration",
            503,
            (
                f"TURN credential TTL must be between {_MIN_TTL_SECONDS} "
                f"and {_MAX_TTL_SECONDS} seconds"
            ),
        )
    return ttl


def _setting(name: str, default: str) -> str:
    configured = current_app.config.get(name)
    if configured is not None:
        return str(configured)
    return os.getenv(name, default)


def _urls(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]
