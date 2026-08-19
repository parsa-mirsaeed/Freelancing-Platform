from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

CALL_TYPES = ("VOICE", "VIDEO")
CALL_STATES = ("INVITED", "ACTIVE", "ENDED")


class CallSession(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "call_sessions"
    __table_args__ = (
        CheckConstraint(
            "call_type IN ('VOICE', 'VIDEO')",
            name="ck_call_sessions_call_type",
        ),
        CheckConstraint(
            "status IN ('INVITED', 'ACTIVE', 'ENDED')",
            name="ck_call_sessions_status",
        ),
        CheckConstraint(
            "caller_user_id <> callee_user_id",
            name="ck_call_sessions_distinct_parties",
        ),
        CheckConstraint(
            "status != 'INVITED' OR (accepted_at IS NULL AND ended_at IS NULL)",
            name="ck_call_sessions_invited_timestamps",
        ),
        CheckConstraint(
            "status != 'ACTIVE' OR (accepted_at IS NOT NULL AND ended_at IS NULL)",
            name="ck_call_sessions_active_timestamps",
        ),
        CheckConstraint(
            "status != 'ENDED' OR ended_at IS NOT NULL",
            name="ck_call_sessions_ended_timestamp",
        ),
        CheckConstraint(
            "ended_by_user_id IS NULL OR ended_by_user_id = caller_user_id "
            "OR ended_by_user_id = callee_user_id",
            name="ck_call_sessions_ended_by_party",
        ),
        UniqueConstraint(
            "caller_user_id",
            "client_call_id",
            name="uq_call_sessions_caller_client_call_id",
        ),
        Index("ix_call_sessions_conversation_id", "conversation_id"),
        Index(
            "uq_call_sessions_live_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('INVITED', 'ACTIVE')"),
            sqlite_where=text("status IN ('INVITED', 'ACTIVE')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="RESTRICT"), nullable=False
    )
    caller_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    callee_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    client_call_id: Mapped[str] = mapped_column(String(80), nullable=False)
    call_type: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="INVITED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
