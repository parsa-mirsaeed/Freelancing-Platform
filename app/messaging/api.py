from __future__ import annotations

import uuid

from flask import Blueprint, g, jsonify, request

from app.errors import ApiError
from app.identity.auth import require_access_token
from app.identity.models import User
from app.messaging.service import (
    get_or_create_contract_conversation,
    list_conversations,
    list_messages,
    mark_delivered,
    mark_read,
    send_message,
    serialize_conversation,
    serialize_message,
)
from app.realtime.publisher import (
    publish_delivery_receipt,
    publish_message,
    publish_read_receipt,
)

messaging_bp = Blueprint("messaging", __name__, url_prefix="/api/v1")


@messaging_bp.post("/contracts/<uuid:contract_id>/conversation")
@require_access_token
def contract_conversation(contract_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    conversation = get_or_create_contract_conversation(user=user, contract_id=contract_id)
    return jsonify(serialize_conversation(conversation)), 200


@messaging_bp.get("/conversations")
@require_access_token
def conversations():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify([serialize_conversation(item) for item in list_conversations(user=user)])


@messaging_bp.get("/conversations/<uuid:conversation_id>/messages")
@require_access_token
def messages(conversation_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    try:
        after = int(request.args.get("after", "0"))
        limit = int(request.args.get("limit", "50"))
    except ValueError as exc:
        raise ApiError(
            "validation_error",
            "Invalid pagination",
            422,
            "after and limit are integers",
        ) from exc
    items = list_messages(user=user, conversation_id=conversation_id, after=after, limit=limit)
    return jsonify([serialize_message(item) for item in items])


@messaging_bp.post("/conversations/<uuid:conversation_id>/messages")
@require_access_token
def create_message(conversation_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    body = request.get_json(silent=True) or {}
    if "client_message_id" not in body:
        raise ApiError("validation_error", "Invalid message", 422, "client_message_id is required")
    raw_attachment_ids = body.get("attachment_ids", [])
    if not isinstance(raw_attachment_ids, list):
        raise ApiError(
            "validation_error", "Invalid attachments", 422, "attachment_ids must be a list"
        )
    try:
        attachment_ids = [uuid.UUID(str(value)) for value in raw_attachment_ids]
    except (TypeError, ValueError) as exc:
        raise ApiError(
            "validation_error", "Invalid attachments", 422, "attachment_ids contain invalid UUIDs"
        ) from exc
    message = send_message(
        user=user,
        conversation_id=conversation_id,
        client_message_id=str(body["client_message_id"]),
        body=str(body.get("body", "")),
        attachment_ids=attachment_ids,
    )
    payload = serialize_message(message)
    publish_message(payload)
    return jsonify(payload), 201


@messaging_bp.post("/conversations/<uuid:conversation_id>/delivered")
@require_access_token
def delivered_messages(conversation_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    through_sequence = _through_sequence()
    sequence = mark_delivered(
        user=user, conversation_id=conversation_id, through_sequence=through_sequence
    )
    payload = {
        "conversation_id": str(conversation_id),
        "user_id": str(user.id),
        "through_sequence": sequence,
    }
    publish_delivery_receipt(payload)
    return jsonify(payload)


@messaging_bp.post("/conversations/<uuid:conversation_id>/read")
@require_access_token
def read_messages(conversation_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    through_sequence = _through_sequence()
    sequence = mark_read(
        user=user, conversation_id=conversation_id, through_sequence=through_sequence
    )
    payload = {
        "conversation_id": str(conversation_id),
        "user_id": str(user.id),
        "through_sequence": sequence,
    }
    publish_read_receipt(payload)
    return jsonify(payload)


def _through_sequence() -> int:
    body = request.get_json(silent=True) or {}
    if "through_sequence" not in body:
        raise ApiError("validation_error", "Invalid receipt", 422, "through_sequence is required")
    try:
        return int(body["through_sequence"])
    except (TypeError, ValueError) as exc:
        raise ApiError(
            "validation_error",
            "Invalid receipt",
            422,
            "through_sequence must be an integer",
        ) from exc
