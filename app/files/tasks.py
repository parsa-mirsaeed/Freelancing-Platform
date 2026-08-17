from __future__ import annotations

import uuid

from celery import shared_task
from flask import current_app
from sqlalchemy import select

from app.audit.service import record_audit_event
from app.common.models import OutboxEvent
from app.extensions import db
from app.files.config import FileSettings
from app.files.models import FileObject, FileScanReceipt
from app.files.scanner import BasicFileScanner, ClamAVScanner, FileScanner
from app.files.storage import ObjectStorage


@shared_task(
    name="files.drain_scan_outbox",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    soft_time_limit=30,
    time_limit=40,
)  # type: ignore[untyped-decorator]
def drain_scan_outbox(limit: int = 50) -> int:
    event_ids = list(
        db.session.scalars(
            select(OutboxEvent.id)
            .outerjoin(FileScanReceipt, FileScanReceipt.outbox_event_id == OutboxEvent.id)
            .where(
                OutboxEvent.event_type == "file.scan.requested",
                FileScanReceipt.id.is_(None),
            )
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
        )
    )
    processed = 0
    for event_id in event_ids:
        if _process_scan_event(event_id):
            processed += 1
    return processed


def _process_scan_event(event_id: uuid.UUID) -> bool:
    event = db.session.scalar(
        select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update()
    )
    if event is None:
        return False
    existing = db.session.scalar(
        select(FileScanReceipt.id).where(FileScanReceipt.outbox_event_id == event.id)
    )
    if existing is not None:
        return False
    file_id = uuid.UUID(str(event.payload["file_id"]))
    file_object = db.session.scalar(
        select(FileObject).where(FileObject.id == file_id).with_for_update()
    )
    if file_object is None:
        db.session.add(FileScanReceipt(outbox_event_id=event.id, file_id=file_id))
        db.session.commit()
        return True
    if file_object.status != "SCANNING":
        db.session.add(FileScanReceipt(outbox_event_id=event.id, file_id=file_object.id))
        db.session.commit()
        return True

    settings = FileSettings.from_env(environment=str(current_app.config["APP_ENV"]))
    storage = ObjectStorage(settings)
    scanner = _scanner(settings)
    result = scanner.scan(
        storage.iter_bytes(object_key=file_object.object_key), mime_type=file_object.mime_type
    )
    if file_object.sha256 is not None and file_object.sha256 != result.sha256:
        result = type(result)(False, result.sha256, "uploaded content SHA-256 does not match")
    file_object.sha256 = result.sha256
    file_object.status = "SAFE" if result.safe else "REJECTED"
    file_object.rejection_reason = result.reason
    db.session.add(FileScanReceipt(outbox_event_id=event.id, file_id=file_object.id))
    record_audit_event(
        action="file.scan_completed",
        resource_type="file",
        resource_id=str(file_object.id),
        actor_user_id=None,
        metadata={"status": file_object.status, "reason": file_object.rejection_reason},
    )
    db.session.commit()
    return True


def _scanner(settings: FileSettings) -> FileScanner:
    if settings.scanner_mode == "basic":
        return BasicFileScanner()
    if settings.scanner_mode == "clamav":
        return ClamAVScanner(host=settings.clamav_host, port=settings.clamav_port)
    raise RuntimeError("FILE_SCANNER_MODE must be 'basic' or 'clamav'")
