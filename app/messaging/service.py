from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.common.models import OutboxEvent
from app.contracts.models import Contract
from app.errors import ApiError
from app.extensions import db
from app.files.models import FileObject
from app.identity.models import User
from app.messaging.models import (
    Conversation,
    ConversationMember,
    Message,
    MessageAttachment,
    MessageReceipt,
)
from app.messaging.policies import is_conversation_member
from app.observability import observe_histogram

MAX_MESSAGE_BODY = 8000
MAX_ATTACHMENTS = 10


def get_or_create_contract_conversation(*, user: User, contract_id: uuid.UUID) -> Conversation:
    contract = db.session.get(Contract, contract_id)
    if contract is None:
        raise ApiError("contract_not_found", "Contract not found", 404, "Contract was not found")
    if user.id not in {contract.employer_user_id, contract.freelancer_user_id}:
        raise ApiError("forbidden", "Forbidden", 403, "Only contract parties may open this chat")

    existing = db.session.scalar(
        _conversation_query().where(Conversation.contract_id == contract.id)
    )
    if existing is not None:
        return existing

    conversation = Conversation(id=uuid.uuid4(), contract_id=contract.id)
    conversation.members.extend(
        [
            ConversationMember(user_id=contract.employer_user_id),
            ConversationMember(user_id=contract.freelancer_user_id),
        ]
    )
    db.session.add(conversation)
    record_audit_event(
        action="conversation.created",
        resource_type="conversation",
        resource_id=str(conversation.id),
        actor_user_id=user.id,
        metadata={"contract_id": str(contract.id)},
    )
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        concurrent = db.session.scalar(
            _conversation_query().where(Conversation.contract_id == contract.id)
        )
        if concurrent is None:
            raise
        return concurrent
    return get_conversation_for_user(user=user, conversation_id=conversation.id)


def list_conversations(*, user: User) -> list[Conversation]:
    return list(
        db.session.scalars(
            _conversation_query()
            .join(ConversationMember)
            .where(ConversationMember.user_id == user.id)
            .order_by(Conversation.created_at.desc())
        ).unique()
    )


def get_conversation_for_user(*, user: User, conversation_id: uuid.UUID) -> Conversation:
    conversation = db.session.scalar(
        _conversation_query().where(Conversation.id == conversation_id)
    )
    if conversation is None:
        raise ApiError(
            "conversation_not_found", "Conversation not found", 404, "Conversation was not found"
        )
    if not is_conversation_member(user, conversation):
        raise ApiError("forbidden", "Forbidden", 403, "You are not a conversation member")
    return conversation


def list_messages(
    *, user: User, conversation_id: uuid.UUID, after: int, limit: int
) -> list[Message]:
    get_conversation_for_user(user=user, conversation_id=conversation_id)
    if after < 0:
        raise ApiError("validation_error", "Invalid cursor", 422, "after must be non-negative")
    if limit < 1 or limit > 100:
        raise ApiError("validation_error", "Invalid limit", 422, "limit must be between 1 and 100")
    return list(
        db.session.scalars(
            _message_query()
            .where(Message.conversation_id == conversation_id, Message.sequence > after)
            .order_by(Message.sequence.asc())
            .limit(limit)
        ).unique()
    )


def send_message(
    *,
    user: User,
    conversation_id: uuid.UUID,
    client_message_id: str,
    body: str,
    attachment_ids: list[uuid.UUID],
) -> Message:
    normalized_client_id = client_message_id.strip()
    normalized_body = body.strip()
    if not normalized_client_id or len(normalized_client_id) > 80:
        raise ApiError(
            "validation_error",
            "Invalid client message id",
            422,
            "client_message_id must be between 1 and 80 characters",
        )
    if len(normalized_body) > MAX_MESSAGE_BODY:
        raise ApiError("validation_error", "Message too long", 422, "Message body is too long")
    if len(attachment_ids) > MAX_ATTACHMENTS or len(set(attachment_ids)) != len(attachment_ids):
        raise ApiError(
            "validation_error",
            "Invalid attachments",
            422,
            "A message may include at most 10 distinct attachments",
        )
    if not normalized_body and not attachment_ids:
        raise ApiError(
            "validation_error", "Empty message", 422, "A message needs body text or an attachment"
        )

    conversation = db.session.scalar(
        _conversation_query().where(Conversation.id == conversation_id).with_for_update()
    )
    if conversation is None:
        raise ApiError(
            "conversation_not_found", "Conversation not found", 404, "Conversation was not found"
        )
    if not is_conversation_member(user, conversation):
        raise ApiError("forbidden", "Forbidden", 403, "You are not a conversation member")

    prior = db.session.scalar(
        _message_query().where(
            Message.conversation_id == conversation.id,
            Message.sender_user_id == user.id,
            Message.client_message_id == normalized_client_id,
        )
    )
    if prior is not None:
        prior_attachment_ids = sorted(str(item.file_id) for item in prior.attachments)
        incoming_attachment_ids = sorted(str(file_id) for file_id in attachment_ids)
        if prior.body != normalized_body or prior_attachment_ids != incoming_attachment_ids:
            raise ApiError(
                "client_message_id_reused",
                "Client message id reused",
                409,
                "client_message_id was already used for different message content",
            )
        return prior

    files = _validated_attachments(user=user, attachment_ids=attachment_ids)
    sequence = conversation.next_sequence
    conversation.next_sequence += 1
    message = Message(
        conversation_id=conversation.id,
        sender_user_id=user.id,
        sequence=sequence,
        client_message_id=normalized_client_id,
        body=normalized_body,
    )
    message.attachments.extend(MessageAttachment(file_id=file_object.id) for file_object in files)
    db.session.add(message)
    db.session.flush()

    recipient_ids = [member.user_id for member in conversation.members if member.user_id != user.id]
    db.session.add(
        OutboxEvent(
            event_type="message.created",
            aggregate_type="conversation",
            aggregate_id=str(conversation.id),
            payload={
                "message_id": str(message.id),
                "conversation_id": str(conversation.id),
                "sender_user_id": str(user.id),
                "recipient_user_ids": [str(user_id) for user_id in recipient_ids],
                "sequence": sequence,
            },
        )
    )
    for recipient_id in recipient_ids:
        db.session.add(
            OutboxEvent(
                event_type="notification.requested",
                aggregate_type="message",
                aggregate_id=str(message.id),
                payload={
                    "user_id": str(recipient_id),
                    "event_type": "message.created",
                    "title": "New message",
                    "body": normalized_body[:160] or "New attachment",
                    "dedupe_key": f"message:{message.id}",
                    "payload": {
                        "conversation_id": str(conversation.id),
                        "message_id": str(message.id),
                        "sequence": sequence,
                    },
                },
            )
        )
    record_audit_event(
        action="message.created",
        resource_type="message",
        resource_id=str(message.id),
        actor_user_id=user.id,
        metadata={"conversation_id": str(conversation.id), "sequence": sequence},
    )
    db.session.commit()
    return db.session.scalar(_message_query().where(Message.id == message.id)) or message


def mark_delivered(*, user: User, conversation_id: uuid.UUID, through_sequence: int) -> int:
    return _mark_receipts(
        user=user,
        conversation_id=conversation_id,
        through_sequence=through_sequence,
        receipt_types=("DELIVERED",),
        update_read_cursor=False,
    )


def mark_read(*, user: User, conversation_id: uuid.UUID, through_sequence: int) -> int:
    return _mark_receipts(
        user=user,
        conversation_id=conversation_id,
        through_sequence=through_sequence,
        receipt_types=("DELIVERED", "READ"),
        update_read_cursor=True,
    )


def _mark_receipts(
    *,
    user: User,
    conversation_id: uuid.UUID,
    through_sequence: int,
    receipt_types: tuple[str, ...],
    update_read_cursor: bool,
) -> int:
    conversation = db.session.scalar(
        _conversation_query().where(Conversation.id == conversation_id).with_for_update()
    )
    if conversation is None:
        raise ApiError(
            "conversation_not_found", "Conversation not found", 404, "Conversation was not found"
        )
    member = next((item for item in conversation.members if item.user_id == user.id), None)
    if member is None:
        raise ApiError("forbidden", "Forbidden", 403, "You are not a conversation member")
    max_sequence = max(0, conversation.next_sequence - 1)
    if through_sequence < 0 or through_sequence > max_sequence:
        raise ApiError(
            "validation_error", "Invalid receipt cursor", 422, "through_sequence is out of range"
        )
    if update_read_cursor and through_sequence <= member.last_read_sequence:
        return member.last_read_sequence

    messages = list(
        db.session.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.sequence <= through_sequence,
                Message.sender_user_id != user.id,
            )
        )
    )
    message_ids = [message.id for message in messages]
    existing: set[tuple[uuid.UUID, str]] = set()
    if message_ids:
        existing = set(
            db.session.execute(
                select(MessageReceipt.message_id, MessageReceipt.receipt_type).where(
                    MessageReceipt.user_id == user.id,
                    MessageReceipt.receipt_type.in_(receipt_types),
                    MessageReceipt.message_id.in_(message_ids),
                )
            ).tuples()
        )

    now = datetime.now(UTC)
    delivery_latencies = [
        max(0.0, (now - _as_utc(message.created_at)).total_seconds())
        for message in messages
        if "DELIVERED" in receipt_types and (message.id, "DELIVERED") not in existing
    ]
    db.session.add_all(
        MessageReceipt(message_id=message.id, user_id=user.id, receipt_type=receipt_type)
        for message in messages
        for receipt_type in receipt_types
        if (message.id, receipt_type) not in existing
    )
    if update_read_cursor:
        member.last_read_sequence = through_sequence
    event_type = "message.read" if update_read_cursor else "message.delivered"
    db.session.add(
        OutboxEvent(
            event_type=event_type,
            aggregate_type="conversation",
            aggregate_id=str(conversation.id),
            payload={"user_id": str(user.id), "through_sequence": through_sequence},
        )
    )
    db.session.commit()
    for latency in delivery_latencies:
        observe_histogram("message_delivery_duration_seconds", latency)
    return through_sequence


def serialize_conversation(conversation: Conversation) -> dict[str, Any]:
    return {
        "id": str(conversation.id),
        "contract_id": str(conversation.contract_id) if conversation.contract_id else None,
        "next_sequence": conversation.next_sequence,
        "members": [
            {
                "user_id": str(member.user_id),
                "last_read_sequence": member.last_read_sequence,
                "joined_at": member.joined_at.isoformat(),
            }
            for member in conversation.members
        ],
        "created_at": conversation.created_at.isoformat(),
    }


def serialize_message(message: Message) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "sender_user_id": str(message.sender_user_id),
        "sequence": message.sequence,
        "client_message_id": message.client_message_id,
        "body": message.body,
        "attachments": [str(item.file_id) for item in message.attachments],
        "receipts": [
            {
                "user_id": str(receipt.user_id),
                "type": receipt.receipt_type,
                "created_at": receipt.created_at.isoformat(),
            }
            for receipt in message.receipts
        ],
        "created_at": message.created_at.isoformat(),
    }


def _validated_attachments(*, user: User, attachment_ids: list[uuid.UUID]) -> list[FileObject]:
    if not attachment_ids:
        return []
    files = list(db.session.scalars(select(FileObject).where(FileObject.id.in_(attachment_ids))))
    if len(files) != len(attachment_ids):
        raise ApiError(
            "file_not_found",
            "File not found",
            404,
            "One or more attachments were not found",
        )
    for file_object in files:
        if file_object.owner_user_id != user.id:
            raise ApiError("forbidden", "Forbidden", 403, "You can only attach files you own")
        if file_object.status != "SAFE":
            raise ApiError(
                "unsafe_attachment", "Unsafe attachment", 409, "Only SAFE files can be attached"
            )
        if file_object.purpose != "MESSAGE_ATTACHMENT":
            raise ApiError(
                "invalid_attachment_purpose",
                "Invalid attachment purpose",
                409,
                "Only MESSAGE_ATTACHMENT files can be attached to messages",
            )
    by_id = {file_object.id: file_object for file_object in files}
    return [by_id[file_id] for file_id in attachment_ids]


def _conversation_query() -> Select[tuple[Conversation]]:
    return select(Conversation).options(selectinload(Conversation.members))


def _message_query() -> Select[tuple[Message]]:
    return select(Message).options(
        selectinload(Message.attachments),
        selectinload(Message.receipts),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
