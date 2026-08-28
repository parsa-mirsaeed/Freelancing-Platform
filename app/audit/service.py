from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from flask import g, has_request_context

from app.audit.models import AuditEvent
from app.extensions import db

_STATE_HASH_REQUIRED_ACTIONS = frozenset(
    {
        "contract.created",
        "contract.signed",
        "contract.activated",
        "contract.cancelled",
        "identity.login_risk",
        "identity.login_succeeded",
        "identity.mfa_enrollment_started",
        "identity.mfa_enabled",
        "identity.mfa_challenge_failed",
        "identity.mfa_verified",
        "identity.mfa_recovery_code_used",
        "payout_provider_account.configured",
        "payout_provider_account.disabled",
        "payout.reserved",
        "payout.succeeded",
        "payout.failed",
        "milestone.released",
        "refund.reserved",
        "milestone.refunded",
        "refund.failed",
        "dispute.opened",
        "dispute.transitioned",
        "dispute.resolved",
    }
)


def audit_state_hash(state: Mapping[str, object] | None) -> str | None:
    if state is None:
        return None
    encoded = json.dumps(
        dict(state),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_audit_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def record_audit_event(
    *,
    action: str,
    resource_type: str,
    actor_user_id: uuid.UUID | None = None,
    resource_id: str | None = None,
    previous_state: Mapping[str, object] | None = None,
    new_state: Mapping[str, object] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    metadata_json = metadata or {}
    if previous_state is None:
        previous_state = _metadata_state(metadata_json, "before")
    if new_state is None:
        new_state = _metadata_state(metadata_json, "after")
    if action in _STATE_HASH_REQUIRED_ACTIONS and (previous_state is None or new_state is None):
        raise ValueError(f"High-risk audit action {action} requires previous and new state")
    event = AuditEvent(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=getattr(g, "request_id", None) if has_request_context() else None,
        previous_state_hash=audit_state_hash(previous_state),
        new_state_hash=audit_state_hash(new_state),
        metadata_json=metadata_json,
    )
    db.session.add(event)
    return event


def _metadata_state(metadata: dict[str, Any], key: str) -> Mapping[str, object] | None:
    candidate = metadata.get(key)
    if isinstance(candidate, dict):
        return candidate
    return None


def _audit_json_default(value: object) -> object:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"Unsupported audit state value: {type(value).__name__}")
