from __future__ import annotations

import uuid

from flask import request
from flask_socketio import emit, join_room

from app.errors import ApiError
from app.extensions import db, socketio
from app.identity.models import User
from app.messaging.service import (
    get_conversation_for_user,
    mark_delivered,
    mark_read,
    send_message,
    serialize_message,
)
from app.realtime.auth import authenticate_socket_token, load_socket_user
from app.realtime.presence import bind_socket, heartbeat, socket_identity, unbind_socket
from app.realtime.publisher import (
    publish_delivery_receipt,
    publish_message,
    publish_read_receipt,
)


@socketio.on("connect")  # type: ignore[untyped-decorator]
def connect(auth: dict[str, object] | None) -> bool | None:
    token = str(auth.get("token", "")) if auth else ""
    principal = authenticate_socket_token(token)
    if principal is None:
        return False
    sid = _sid()
    bind_socket(
        user_id=principal.user.id,
        session_id=principal.session_id,
        sid=sid,
        access_expires_at=principal.access_expires_at,
    )
    join_room(f"user:{principal.user.id}")
    return None


@socketio.on("disconnect")  # type: ignore[untyped-decorator]
def disconnect() -> None:
    identity = socket_identity(_sid())
    if identity is not None:
        user_id, _session_id = identity
        unbind_socket(user_id=user_id, sid=_sid())


@socketio.on("presence.heartbeat")  # type: ignore[untyped-decorator]
def presence_heartbeat() -> dict[str, object]:
    user = _require_socket_user()
    heartbeat(user_id=user.id, sid=_sid())
    return {"ok": True}


@socketio.on("conversation.join")  # type: ignore[untyped-decorator]
def join_conversation(data: dict[str, object]) -> dict[str, object]:
    user = _require_socket_user()
    try:
        conversation_id = uuid.UUID(str(data["conversation_id"]))
    except (KeyError, ValueError) as exc:
        return _socket_error("validation_error", str(exc))
    try:
        conversation = get_conversation_for_user(user=user, conversation_id=conversation_id)
    except ApiError as exc:
        return _api_error(exc)
    join_room(f"conversation:{conversation.id}")
    if conversation.contract_id is not None:
        join_room(f"contract:{conversation.contract_id}")
    return {"ok": True, "conversation_id": str(conversation.id)}


@socketio.on("message.send")  # type: ignore[untyped-decorator]
def message_send(data: dict[str, object]) -> dict[str, object]:
    user = _require_socket_user()
    try:
        conversation_id = uuid.UUID(str(data["conversation_id"]))
        raw_attachment_ids = data.get("attachment_ids", [])
        if not isinstance(raw_attachment_ids, list):
            raise TypeError("attachment_ids must be a list")
        attachment_ids = [uuid.UUID(str(value)) for value in raw_attachment_ids]
        client_message_id = str(data["client_message_id"])
        body = str(data.get("body", ""))
    except (KeyError, TypeError, ValueError) as exc:
        return _socket_error("validation_error", str(exc))
    try:
        message = send_message(
            user=user,
            conversation_id=conversation_id,
            client_message_id=client_message_id,
            body=body,
            attachment_ids=attachment_ids,
        )
    except ApiError as exc:
        db.session.rollback()
        return _api_error(exc)
    payload = serialize_message(message)
    publish_message(payload)
    return {"ok": True, "message": payload}


@socketio.on("message.delivered")  # type: ignore[untyped-decorator]
def message_delivered(data: dict[str, object]) -> dict[str, object]:
    user = _require_socket_user()
    try:
        conversation_id = uuid.UUID(str(data["conversation_id"]))
        through_sequence = int(str(data["through_sequence"]))
    except (KeyError, TypeError, ValueError) as exc:
        return _socket_error("validation_error", str(exc))
    try:
        sequence = mark_delivered(
            user=user,
            conversation_id=conversation_id,
            through_sequence=through_sequence,
        )
    except ApiError as exc:
        db.session.rollback()
        return _api_error(exc)
    payload = {
        "conversation_id": str(conversation_id),
        "user_id": str(user.id),
        "through_sequence": sequence,
    }
    publish_delivery_receipt(payload)
    return {"ok": True, **payload}


@socketio.on("message.read")  # type: ignore[untyped-decorator]
def message_read(data: dict[str, object]) -> dict[str, object]:
    user = _require_socket_user()
    try:
        conversation_id = uuid.UUID(str(data["conversation_id"]))
        through_sequence = int(str(data["through_sequence"]))
    except (KeyError, TypeError, ValueError) as exc:
        return _socket_error("validation_error", str(exc))
    try:
        sequence = mark_read(
            user=user,
            conversation_id=conversation_id,
            through_sequence=through_sequence,
        )
    except ApiError as exc:
        db.session.rollback()
        return _api_error(exc)
    payload = {
        "conversation_id": str(conversation_id),
        "user_id": str(user.id),
        "through_sequence": sequence,
    }
    publish_read_receipt(payload)
    return {"ok": True, **payload}


def _sid() -> str:
    return str(getattr(request, "sid", ""))


def _require_socket_user() -> User:
    identity = socket_identity(_sid())
    if identity is None:
        emit("error", {"type": "unauthorized", "detail": "Socket is not authenticated"})
        raise ConnectionRefusedError("Socket is not authenticated")
    user_id, session_id = identity
    user = load_socket_user(user_id=user_id, session_id=session_id)
    if user is None:
        emit("error", {"type": "unauthorized", "detail": "Socket session is unavailable"})
        raise ConnectionRefusedError("Socket session is unavailable")
    return user


def _api_error(error: ApiError) -> dict[str, object]:
    return _socket_error(error.type, error.detail, status=error.status)


def _socket_error(error_type: str, detail: str, *, status: int = 422) -> dict[str, object]:
    return {"ok": False, "error": {"type": error_type, "status": status, "detail": detail}}
