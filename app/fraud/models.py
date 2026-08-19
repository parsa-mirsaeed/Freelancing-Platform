from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class RiskAssessment(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "risk_assessments"
    __table_args__ = (
        CheckConstraint(
            "risk_score_basis_points >= 0 AND risk_score_basis_points <= 10000",
            name="ck_risk_assessments_score_range",
        ),
        CheckConstraint(
            "review_status IN ('NOT_REQUIRED', 'PENDING', 'CLEARED', 'ESCALATED')",
            name="ck_risk_assessments_review_status",
        ),
        CheckConstraint(
            "(review_status IN ('NOT_REQUIRED', 'PENDING') AND reviewer_user_id IS NULL "
            "AND reviewed_at IS NULL) OR "
            "(review_status IN ('CLEARED', 'ESCALATED') AND reviewer_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL)",
            name="ck_risk_assessments_review_metadata",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subject_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(80), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    risk_score_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    reasons_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    signals_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
