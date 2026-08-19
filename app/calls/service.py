from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.calls.models import CALL_TYPES, CallSession
from app.common.models import OutboxEvent
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.messaging.models import Conversation

LIVE_CALL_STATES = ("INVITED", "ACTIVE")
MAX_SIGNAL_BYTES = 262_144
MAX_END_REASON = 500


def invite_call(
    *,
    user: User,
    conversation_id: uuid.UUID,
    client_call_id: str,
    call_type: str,
) -> tuple[CallSession, bool]:
    normalized_client_id = client_call_id.strip()
    normalized_type = call_type.strip().upper()
    if not normalized_client_id or len(normalized_client_id) > 80:
        raise ApiError(
            "validation_error",
            "Invalid client call id",
            422,
            "client_call_id must be between 1 and 80 characters",
        )
    if normalized_type not in CALL_TYPES:
        raise ApiError(
            "validation_error",
            "Invalid call type",
            422,
            "call_type must be VOICE or VIDEO",
        )

    conversation = db.session.scalar(
        _conversation_query().where(Conversation.id == conversation_id).with_for_update()
    )
    if conversation is None:
        raise ApiError(
            "conversation_not_found",
            "Conversation not found",
            404,
            "Conversation was not found",
        )
    member_ids = {member.user_id for member in conversation.members}
    if user.id not in member_ids:
        raise ApiError("forbidden", "Forbidden", 403, "You are not a conversation member")
    if len(member_ids) != 2:
        raise ApiError(
            "unsupported_call_topology",
            "Unsupported call topology",
            409,
            "This phase supports only one-to-one calls",
        )
    callee_user_id = next(member_id for member_id in member_ids if member_id != user.id)

    prior = db.session.scalar(
        _call_query().where(
            CallSession.caller_user_id == user.id,
            CallSession.client_call_id == normalized_client_id,
        )
    )
    if prior is not None:
        if prior.conversation_id != conversation.id or prior.call_type != normalized_type:
            raise ApiError(
                "client_call_id_reused",
                "Client call id reused",
                409,
                "client_call_id was already used for different call content",
            )
        return prior, False

    live = db.session.scalar(
        _call_query().where(
            CallSession.conversation_id == conversation.id,
            CallSession.status.in_(LIVE_CALL_STATES),
        )
    )
    if live is not None:
        raise ApiError(
            "conversation_busy",
            "Conversation already has a live call",
            409,
            "Only one invited or active call is allowed per conversation",
        )

    call = CallSession(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        caller_user_id=user.id,
        callee_user_id=callee_user_id,
        client_call_id=normalized_client_id,
        call_type=normalized_type,
        status="INVITED",
    )
    db.session.add(call)
    db.session.add(
        OutboxEvent(
            event_type="notification.requested",
            aggregate_type="call",
            aggregate_id=str(call.id),
            payload={
                "user_id": str(callee_user_id),
                "event_type": "call.invited",
                "title": "Incoming call",
                "body": f"Incoming {normalized_type.lower()} call",
                "dedupe_key": f"call:{call.id}:invite",
                "payload": {
                    "call_id": str(call.id),
                    "conversation_id": str(conversation.id),
                    "caller_user_id": str(user.id),
                    "call_type": normalized_type,
                },
            },
        )
    )
    record_audit_event(
        action="call.invited",
        resource_type="call",
        resource_id=str(call.id),
        actor_user_id=user.id,
        metadata={
            "conversation_id": str(conversation.id),
            "callee_user_id": str(callee_user_id),
            "call_type": normalized_type,
        },
    )
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        concurrent_prior = db.session.scalar(
            _call_query().where(
                CallSession.caller_user_id == user.id,
                CallSession.client_call_id == normalized_client_id,
            )
        )
        if (
            concurrent_prior is not None
            and concurrent_prior.conversation_id == conversation.id
            and concurrent_prior.call_type == normalized_type
        ):
            return concurrent_prior, False
        raise ApiError(
            "conversation_busy",
            "Conversation already has a live call",
            409,
            "Only one invited or active call is allowed per conversation",
        ) from exc
    return call, True


def accept_call(*, user: User, call_id: uuid.UUID) -> tuple[CallSession, bool]:
    call = _locked_call(call_id)
    _require_party(user, call)
    if user.id != call.callee_user_id:
        raise ApiError(
            "forbidden",
            "Forbidden",
            403,
            "Only the invited callee may accept the call",
        )
    if call.status == "ACTIVE":
        return call, False
    if call.status != "INVITED":
        raise ApiError(
            "invalid_call_state",
            "Call cannot be accepted",
            409,
            f"Call in {call.status} cannot be accepted",
        )

    call.status = "ACTIVE"
    call.accepted_at = datetime.now(UTC)
    record_audit_event(
        action="call.accepted",
        resource_type="call",
        resource_id=str(call.id),
        actor_user_id=user.id,
        metadata={"conversation_id": str(call.conversation_id)},
    )
    db.session.commit()
    return call, True


def end_call(*, user: User, call_id: uuid.UUID, reason: str) -> tuple[CallSession, bool]:
    call = _locked_call(call_id)
    _require_party(user, call)
    normalized_reason = reason.strip()
    if len(normalized_reason) > MAX_END_REASON:
        raise ApiError(
            "validation_error",
            "End reason too long",
            422,
            f"reason is limited to {MAX_END_REASON} characters",
        )
    if call.status == "ENDED":
        return call, False

    previous = call.status
    call.status = "ENDED"
    call.ended_at = datetime.now(UTC)
    call.ended_by_user_id = user.id
    call.end_reason = normalized_reason or None
    record_audit_event(
        action="call.ended",
        resource_type="call",
        resource_id=str(call.id),
        actor_user_id=user.id,
        metadata={
            "conversation_id": str(call.conversation_id),
            "previous_status": previous,
            "reason": normalized_reason,
        },
    )
    db.session.commit()
    return call, True


def get_call_for_user(*, user: User, call_id: uuid.UUID) -> CallSession:
    call = db.session.scalar(_call_query().where(CallSession.id == call_id))
    if call is None:
        raise ApiError("call_not_found", "Call not found", 404, "Call was not found")
    _require_party(user, call)
    return call


def signal_peer(*, user: User, call_id: uuid.UUID) -> tuple[CallSession, uuid.UUID]:
    call = get_call_for_user(user=user, call_id=call_id)
    if call.status != "ACTIVE":
        raise ApiError(
            "invalid_call_state",
            "Call is not active",
            409,
            "WebRTC signaling is allowed only after call.accept",
        )
    peer_id = call.callee_user_id if user.id == call.caller_user_id else call.caller_user_id
    return call, peer_id


def validate_session_description(value: object, *, expected_type: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ApiError(
            "validation_error",
            "Invalid session description",
            422,
            "description must be a JSON object",
        )
    description = {str(key): item for key, item in value.items()}
    if description.get("type") != expected_type or not isinstance(description.get("sdp"), str):
        raise ApiError(
            "validation_error",
            "Invalid session description",
            422,
            f"description.type must be {expected_type} and sdp must be a string",
        )
    _ensure_bounded_json(description, "description")
    return description


def validate_ice_candidate(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ApiError(
            "validation_error",
            "Invalid ICE candidate",
            422,
            "candidate must be a JSON object",
        )
    candidate = {str(key): item for key, item in value.items()}
    raw_candidate = candidate.get("candidate")
    if raw_candidate is not None and not isinstance(raw_candidate, str):
        raise ApiError(
            "validation_error",
            "Invalid ICE candidate",
            422,
            "candidate.candidate must be a string when present",
        )
    _ensure_bounded_json(candidate, "candidate")
    return candidate


def serialize_call(call: CallSession) -> dict[str, Any]:
    return {
        "id": str(call.id),
        "conversation_id": str(call.conversation_id),
        "caller_user_id": str(call.caller_user_id),
        "callee_user_id": str(call.callee_user_id),
        "client_call_id": call.client_call_id,
        "call_type": call.call_type,
        "status": call.status,
        "created_at": call.created_at.isoformat(),
        "accepted_at": call.accepted_at.isoformat() if call.accepted_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "ended_by_user_id": str(call.ended_by_user_id) if call.ended_by_user_id else None,
        "end_reason": call.end_reason,
    }


def _ensure_bounded_json(payload: dict[str, object], field: str) -> None:
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    except (TypeError, ValueError) as exc:
        raise ApiError(
            "validation_error",
            f"Invalid {field}",
            422,
            f"{field} must contain JSON-serializable values",
        ) from exc
    if len(encoded) > MAX_SIGNAL_BYTES:
        raise ApiError(
            "payload_too_large",
            "Signaling payload too large",
            422,
            f"{field} exceeds {MAX_SIGNAL_BYTES} bytes",
        )


def _locked_call(call_id: uuid.UUID) -> CallSession:
    call = db.session.scalar(_call_query().where(CallSession.id == call_id).with_for_update())
    if call is None:
        raise ApiError("call_not_found", "Call not found", 404, "Call was not found")
    return call


def _require_party(user: User, call: CallSession) -> None:
    if user.id not in {call.caller_user_id, call.callee_user_id}:
        raise ApiError("forbidden", "Forbidden", 403, "Only call parties may perform this action")


def _call_query() -> Select[tuple[CallSession]]:
    return select(CallSession)


def _conversation_query() -> Select[tuple[Conversation]]:
    return select(Conversation).options(selectinload(Conversation.members))
