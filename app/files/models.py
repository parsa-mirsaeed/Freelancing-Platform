from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class FileObject(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "file_objects"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="ck_file_objects_size_positive"),
        CheckConstraint(
            "status IN ('QUARANTINED', 'SCANNING', 'SAFE', 'REJECTED')",
            name="ck_file_objects_status",
        ),
        CheckConstraint(
            "purpose IN ('MESSAGE_ATTACHMENT', 'PORTFOLIO', 'PROJECT_ATTACHMENT', "
            "'DISPUTE_EVIDENCE')",
            name="ck_file_objects_purpose",
        ),
        UniqueConstraint("object_key", name="uq_file_objects_object_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUARANTINED")
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class FileScanReceipt(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "file_scan_receipts"
    __table_args__ = (
        UniqueConstraint("outbox_event_id", name="uq_file_scan_receipts_outbox_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    outbox_event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("outbox_events.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("file_objects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
