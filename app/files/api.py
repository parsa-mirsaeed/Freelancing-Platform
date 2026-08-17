from __future__ import annotations

import uuid

from flask import Blueprint, g, jsonify, request

from app.errors import ApiError
from app.files.service import complete_upload, create_download, create_upload, serialize_file
from app.identity.auth import require_access_token
from app.identity.models import User

files_bp = Blueprint("files", __name__, url_prefix="/api/v1/files")


@files_bp.post("/uploads")
@require_access_token
def request_upload():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    body = request.get_json(silent=True) or {}
    required = ("original_name", "mime_type", "size_bytes", "purpose")
    if any(key not in body for key in required):
        raise ApiError("validation_error", "Invalid upload", 422, "Upload metadata is incomplete")
    try:
        size_bytes = int(body["size_bytes"])
    except (TypeError, ValueError) as exc:
        raise ApiError(
            "validation_error", "Invalid upload", 422, "size_bytes must be an integer"
        ) from exc
    file_object, upload_url = create_upload(
        user=user,
        original_name=str(body["original_name"]),
        mime_type=str(body["mime_type"]),
        size_bytes=size_bytes,
        purpose=str(body["purpose"]),
        sha256=str(body["sha256"]) if body.get("sha256") is not None else None,
    )
    return jsonify({"file": serialize_file(file_object), "upload_url": upload_url}), 201


@files_bp.post("/<uuid:file_id>/complete")
@require_access_token
def complete(file_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify(serialize_file(complete_upload(user=user, file_id=file_id)))


@files_bp.get("/<uuid:file_id>")
@require_access_token
def download(file_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    file_object, download_url = create_download(user=user, file_id=file_id)
    return jsonify({"file": serialize_file(file_object), "download_url": download_url})
