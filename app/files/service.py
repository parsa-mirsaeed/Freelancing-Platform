from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from flask import current_app
from sqlalchemy import select

from app.audit.service import record_audit_event
from app.common.models import OutboxEvent
from app.errors import ApiError
from app.extensions import db
from app.files.config import FileSettings
from app.files.models import FileObject
from app.files.storage import ObjectStorage
from app.identity.models import User

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "text/plain",
}
_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".txt"}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def create_upload(
    *,
    user: User,
    original_name: str,
    mime_type: str,
    size_bytes: int,
    purpose: str,
    sha256: str | None,
) -> tuple[FileObject, str]:
    settings = _settings()
    clean_name = Path(original_name).name.strip()
    extension = Path(clean_name).suffix.lower()
    if not clean_name or len(clean_name) > 255:
        raise ApiError("validation_error", "Invalid file name", 422, "File name is invalid")
    if extension not in _ALLOWED_EXTENSIONS or mime_type not in _ALLOWED_MIME_TYPES:
        raise ApiError(
            "validation_error",
            "Unsupported file type",
            422,
            "File extension or MIME type is not allowed",
        )
    if size_bytes <= 0 or size_bytes > settings.max_upload_bytes:
        raise ApiError(
            "validation_error",
            "Invalid file size",
            422,
            f"File must be between 1 and {settings.max_upload_bytes} bytes",
        )
    allowed_purposes = {
        "MESSAGE_ATTACHMENT",
        "PORTFOLIO",
        "PROJECT_ATTACHMENT",
        "DISPUTE_EVIDENCE",
    }
    if purpose not in allowed_purposes:
        raise ApiError(
            "validation_error",
            "Invalid file purpose",
            422,
            "Unknown file purpose",
        )
    normalized_sha256 = sha256.lower() if sha256 is not None else None
    if normalized_sha256 is not None and not _SHA256_RE.fullmatch(normalized_sha256):
        raise ApiError("validation_error", "Invalid SHA-256", 422, "sha256 must be 64 hex chars")

    file_id = uuid.uuid4()
    object_key = f"quarantine/{user.id}/{file_id}/{clean_name}"
    file_object = FileObject(
        id=file_id,
        owner_user_id=user.id,
        object_key=object_key,
        original_name=clean_name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        sha256=normalized_sha256,
        purpose=purpose,
        status="QUARANTINED",
    )
    db.session.add(file_object)
    record_audit_event(
        action="file.upload_requested",
        resource_type="file",
        resource_id=str(file_object.id),
        actor_user_id=user.id,
        metadata={"purpose": purpose, "size_bytes": size_bytes, "mime_type": mime_type},
    )
    db.session.commit()
    return file_object, _storage().presign_upload(object_key=object_key, mime_type=mime_type)


def complete_upload(*, user: User, file_id: uuid.UUID) -> FileObject:
    file_object = _owned_file_for_update(user=user, file_id=file_id)
    if file_object.status == "SAFE":
        return file_object
    if file_object.status == "REJECTED":
        raise ApiError("invalid_state", "File rejected", 409, "Rejected files cannot be completed")
    if file_object.status == "SCANNING":
        return file_object

    try:
        metadata = _storage().head(object_key=file_object.object_key)
    except Exception as exc:  # noqa: BLE001 - provider errors become a stable API error
        raise ApiError(
            "upload_missing", "Upload missing", 409, "Uploaded object was not found"
        ) from exc
    actual_size = int(metadata.get("ContentLength", -1))
    content_type = str(metadata.get("ContentType", ""))
    if actual_size != file_object.size_bytes or content_type != file_object.mime_type:
        file_object.status = "REJECTED"
        file_object.rejection_reason = "uploaded object metadata does not match the reservation"
        db.session.commit()
        return file_object

    file_object.status = "SCANNING"
    event = OutboxEvent(
        event_type="file.scan.requested",
        aggregate_type="file",
        aggregate_id=str(file_object.id),
        payload={"file_id": str(file_object.id)},
    )
    db.session.add(event)
    record_audit_event(
        action="file.scan_requested",
        resource_type="file",
        resource_id=str(file_object.id),
        actor_user_id=user.id,
    )
    db.session.commit()
    return file_object


def get_file_for_user(*, user: User, file_id: uuid.UUID) -> FileObject:
    file_object = db.session.get(FileObject, file_id)
    if file_object is None:
        raise ApiError("file_not_found", "File not found", 404, "File was not found")
    if file_object.owner_user_id == user.id:
        return file_object

    from app.messaging.models import ConversationMember, Message, MessageAttachment

    authorized = db.session.scalar(
        select(MessageAttachment.id)
        .join(Message, Message.id == MessageAttachment.message_id)
        .join(ConversationMember, ConversationMember.conversation_id == Message.conversation_id)
        .where(
            MessageAttachment.file_id == file_id,
            ConversationMember.user_id == user.id,
        )
    )
    if authorized is None:
        from app.disputes.models import DisputeEvidence, DisputeParty

        assigned_roles = {assignment.role for assignment in user.roles}
        if "admin" in assigned_roles:
            authorized = db.session.scalar(
                select(DisputeEvidence.id).where(DisputeEvidence.file_id == file_id)
            )
        if authorized is None:
            authorized = db.session.scalar(
                select(DisputeEvidence.id)
                .join(DisputeParty, DisputeParty.dispute_id == DisputeEvidence.dispute_id)
                .where(
                    DisputeEvidence.file_id == file_id,
                    DisputeParty.user_id == user.id,
                )
            )
    if authorized is None:
        raise ApiError("forbidden", "Forbidden", 403, "You may not access this file")
    return file_object


def create_download(*, user: User, file_id: uuid.UUID) -> tuple[FileObject, str]:
    file_object = get_file_for_user(user=user, file_id=file_id)
    if file_object.status != "SAFE":
        raise ApiError(
            "file_unavailable",
            "File unavailable",
            409,
            "Only SAFE files can be downloaded",
        )
    return file_object, _storage().presign_download(
        object_key=file_object.object_key, filename=file_object.original_name
    )


def serialize_file(file_object: FileObject) -> dict[str, Any]:
    return {
        "id": str(file_object.id),
        "original_name": file_object.original_name,
        "mime_type": file_object.mime_type,
        "size_bytes": file_object.size_bytes,
        "sha256": file_object.sha256,
        "purpose": file_object.purpose,
        "status": file_object.status,
        "rejection_reason": file_object.rejection_reason,
        "created_at": file_object.created_at.isoformat(),
    }


def _owned_file_for_update(*, user: User, file_id: uuid.UUID) -> FileObject:
    file_object = db.session.scalar(
        select(FileObject).where(FileObject.id == file_id).with_for_update()
    )
    if file_object is None:
        raise ApiError("file_not_found", "File not found", 404, "File was not found")
    if file_object.owner_user_id != user.id:
        raise ApiError("forbidden", "Forbidden", 403, "Only the file owner may modify it")
    return file_object


def _settings() -> FileSettings:
    return FileSettings.from_env(environment=str(current_app.config["APP_ENV"]))


def _storage() -> ObjectStorage:
    return ObjectStorage(_settings())
