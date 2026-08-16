from __future__ import annotations

import uuid
from typing import Any

from flask import g, has_request_context

from app.audit.models import AuditEvent
from app.extensions import db


def record_audit_event(
    *,
    action: str,
    resource_type: str,
    actor_user_id: uuid.UUID | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=getattr(g, "request_id", None) if has_request_context() else None,
        metadata_json=metadata or {},
    )
    db.session.add(event)
    return event
