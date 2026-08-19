from __future__ import annotations

import uuid
from typing import Any

from flask import current_app

from app.extensions import socketio


def publish_call_event(
    event: str,
    *,
    target_user_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    try:
        socketio.emit(event, payload, to=f"user:{target_user_id}")
    except Exception:  # noqa: BLE001 - persisted call state remains authoritative
        current_app.logger.exception(
            "call signaling broadcast failed",
            extra={"event": event, "target_user_id": str(target_user_id)},
        )
