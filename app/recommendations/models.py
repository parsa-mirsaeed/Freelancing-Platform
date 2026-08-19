from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class ModelRegistryEntry(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "ml_model_versions"
    __table_args__ = (
        CheckConstraint(
            "model_type IN ('RULE_BASED', 'STATISTICAL', 'ML')",
            name="ck_ml_model_versions_model_type",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'SHADOW', 'RETIRED')",
            name="ck_ml_model_versions_status",
        ),
        UniqueConstraint("name", "version", name="uq_ml_model_versions_name_version"),
        Index(
            "uq_ml_model_versions_active_name",
            "name",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_type: Mapped[str] = mapped_column(String(24), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SHADOW")
    config_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    metrics_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    artifact_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class RecommendationRun(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "recommendation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ml_model_versions.id", ondelete="RESTRICT"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class RecommendationPrediction(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "recommendation_predictions"
    __table_args__ = (
        CheckConstraint("rank >= 1", name="ck_recommendation_predictions_rank_positive"),
        CheckConstraint(
            "score_basis_points >= 0 AND score_basis_points <= 10000",
            name="ck_recommendation_predictions_score_range",
        ),
        UniqueConstraint(
            "run_id", "freelancer_user_id", name="uq_recommendation_predictions_run_freelancer"
        ),
        UniqueConstraint("run_id", "rank", name="uq_recommendation_predictions_run_rank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("recommendation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    freelancer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    features_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    reasons_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class RecommendationEvent(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "recommendation_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('IMPRESSION', 'PROFILE_VIEW')",
            name="ck_recommendation_events_event_type",
        ),
        UniqueConstraint(
            "actor_user_id",
            "client_event_id",
            name="uq_recommendation_events_actor_client_event",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("recommendation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    freelancer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    client_event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
