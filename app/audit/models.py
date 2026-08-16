from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class AuditEvent(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


@event.listens_for(AuditEvent, "before_update", propagate=True)
def _prevent_audit_update(_mapper: object, _connection: object, _target: AuditEvent) -> None:
    raise ValueError("audit events are immutable")


@event.listens_for(AuditEvent, "before_delete", propagate=True)
def _prevent_audit_delete(_mapper: object, _connection: object, _target: AuditEvent) -> None:
    raise ValueError("audit events are immutable")
