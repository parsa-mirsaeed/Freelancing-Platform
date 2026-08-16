from __future__ import annotations

from typing import Any

from app.common.models import OutboxEvent
from app.extensions import db


def enqueue_outbox_event(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any] | None = None,
) -> OutboxEvent:
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload or {},
    )
    db.session.add(event)
    return event
