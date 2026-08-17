from __future__ import annotations

import uuid
from typing import Any

from flask import current_app

from app.extensions import socketio


def publish_message(payload: dict[str, Any]) -> None:
    _safe_emit(
        "message.created",
        payload,
        room=f"conversation:{payload['conversation_id']}",
    )


def publish_delivery_receipt(payload: dict[str, Any]) -> None:
    _safe_emit(
        "message.delivered",
        payload,
        room=f"conversation:{payload['conversation_id']}",
    )


def publish_read_receipt(payload: dict[str, Any]) -> None:
    _safe_emit(
        "message.read",
        payload,
        room=f"conversation:{payload['conversation_id']}",
    )


def publish_notification(*, user_id: uuid.UUID, payload: dict[str, Any]) -> None:
    _safe_emit("notification.created", payload, room=f"user:{user_id}")


def _safe_emit(event: str, payload: dict[str, Any], *, room: str) -> None:
    try:
        socketio.emit(event, payload, to=room)
    except Exception:  # noqa: BLE001 - realtime delivery is recoverable after DB commit
        current_app.logger.exception(
            "realtime broadcast failed after persistence", extra={"event": event}
        )
