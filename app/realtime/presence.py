from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import cast

from flask import current_app

from app.extensions import redis_extension

PRESENCE_TTL_SECONDS = 75


def bind_socket(
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    sid: str,
    access_expires_at: datetime,
) -> None:
    client = redis_extension.get_client(current_app)
    expires_in = max(1, int((access_expires_at - datetime.now(UTC)).total_seconds()))
    client.set(
        _socket_key(sid),
        json.dumps({"user_id": str(user_id), "session_id": str(session_id)}),
        ex=expires_in,
    )
    mark_connected(user_id=user_id, sid=sid)


def socket_identity(sid: str) -> tuple[uuid.UUID, uuid.UUID] | None:
    raw = cast(
        str | bytes | bytearray | None,
        redis_extension.get_client(current_app).get(_socket_key(sid)),
    )
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
        return uuid.UUID(str(payload["user_id"])), uuid.UUID(str(payload["session_id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def mark_connected(*, user_id: uuid.UUID, sid: str) -> None:
    client = redis_extension.get_client(current_app)
    key = _presence_key(user_id)
    client.sadd(key, sid)
    client.expire(key, PRESENCE_TTL_SECONDS)


def heartbeat(*, user_id: uuid.UUID, sid: str) -> None:
    client = redis_extension.get_client(current_app)
    key = _presence_key(user_id)
    client.sadd(key, sid)
    client.expire(key, PRESENCE_TTL_SECONDS)


def unbind_socket(*, user_id: uuid.UUID, sid: str) -> None:
    client = redis_extension.get_client(current_app)
    client.delete(_socket_key(sid))
    client.srem(_presence_key(user_id), sid)
    if client.scard(_presence_key(user_id)) == 0:
        client.delete(_presence_key(user_id))


def is_online(user_id: uuid.UUID) -> bool:
    return redis_extension.get_client(current_app).exists(_presence_key(user_id)) == 1


def _presence_key(user_id: uuid.UUID) -> str:
    return f"presence:user:{user_id}"


def _socket_key(sid: str) -> str:
    return f"socket-principal:{sid}"
