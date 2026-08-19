"""AI baseline attribution, model registry, and risk review

Revision ID: 0008_ai_baseline
Revises: 0007_calls
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0008_ai_baseline"
down_revision: str | None = "0007_calls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ml_model_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=80), nullable=False),
        sa.Column("model_type", sa.String(length=24), nullable=False),
        sa.Column("feature_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("artifact_uri", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "model_type IN ('RULE_BASED', 'STATISTICAL', 'ML')",
            name="ck_ml_model_versions_model_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SHADOW', 'RETIRED')",
            name="ck_ml_model_versions_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ml_model_versions"),
        sa.UniqueConstraint("name", "version", name="uq_ml_model_versions_name_version"),
    )
    op.create_index("ix_ml_model_versions_name", "ml_model_versions", ["name"])
    op.create_index(
        "uq_ml_model_versions_active_name",
        "ml_model_versions",
        ["name"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
        sqlite_where=sa.text("status = 'ACTIVE'"),
    )

    model_table = sa.table(
        "ml_model_versions",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("version", sa.String()),
        sa.column("model_type", sa.String()),
        sa.column("feature_version", sa.String()),
        sa.column("status", sa.String()),
        sa.column("config_json", sa.JSON()),
        sa.column("metrics_json", sa.JSON()),
        sa.column("artifact_uri", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        model_table,
        [
            {
                "id": uuid.UUID("11111111-1111-4111-8111-111111111111"),
                "name": "freelancer_matching",
                "version": "rule-v1",
                "model_type": "RULE_BASED",
                "feature_version": "matching-features-v1",
                "status": "ACTIVE",
                "config_json": {
                    "weights": {
                        "skill_match": 4000,
                        "experience": 2000,
                        "price_fit": 1500,
                        "availability": 1000,
                        "reputation": 1500,
                    }
                },
                "metrics_json": {},
                "artifact_uri": None,
                "created_at": now,
            },
            {
                "id": uuid.UUID("22222222-2222-4222-8222-222222222222"),
                "name": "skill_extraction",
                "version": "skill-rules-v1",
                "model_type": "RULE_BASED",
                "feature_version": "skill-text-features-v1",
                "status": "ACTIVE",
                "config_json": {"profile_mutation": False},
                "metrics_json": {},
                "artifact_uri": None,
                "created_at": now,
            },
            {
                "id": uuid.UUID("33333333-3333-4333-8333-333333333333"),
                "name": "price_estimation",
                "version": "pricing-baseline-v1",
                "model_type": "STATISTICAL",
                "feature_version": "pricing-history-v1",
                "status": "ACTIVE",
                "config_json": {"interval": "p25-p75", "minimum_history": 3},
                "metrics_json": {},
                "artifact_uri": None,
                "created_at": now,
            },
            {
                "id": uuid.UUID("44444444-4444-4444-8444-444444444444"),
                "name": "fraud_risk",
                "version": "fraud-rules-v1",
                "model_type": "RULE_BASED",
                "feature_version": "fraud-signals-v1",
                "status": "ACTIVE",
                "config_json": {"human_review_threshold_basis_points": 6000},
                "metrics_json": {},
                "artifact_uri": None,
                "created_at": now,
            },
        ],
    )

    op.create_table(
        "recommendation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("employer_user_id", sa.Uuid(), nullable=False),
        sa.Column("model_version_id", sa.Uuid(), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("feature_version", sa.String(length=80), nullable=False),
        sa.Column("candidate_set_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_recommendation_runs_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["employer_user_id"],
            ["users.id"],
            name="fk_recommendation_runs_employer_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_version_id"],
            ["ml_model_versions.id"],
            name="fk_recommendation_runs_model_version_id_ml_model_versions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recommendation_runs"),
    )
    op.create_index("ix_recommendation_runs_project_id", "recommendation_runs", ["project_id"])
    op.create_index(
        "ix_recommendation_runs_employer_user_id",
        "recommendation_runs",
        ["employer_user_id"],
    )

    op.create_table(
        "recommendation_predictions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_user_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score_basis_points", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("feature_version", sa.String(length=80), nullable=False),
        sa.Column("candidate_set_version", sa.String(length=64), nullable=False),
        sa.Column("features_json", sa.JSON(), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rank >= 1", name="ck_recommendation_predictions_rank_positive"),
        sa.CheckConstraint(
            "score_basis_points >= 0 AND score_basis_points <= 10000",
            name="ck_recommendation_predictions_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["recommendation_runs.id"],
            name="fk_recommendation_predictions_run_id_recommendation_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["freelancer_user_id"],
            ["users.id"],
            name="fk_recommendation_predictions_freelancer_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recommendation_predictions"),
        sa.UniqueConstraint(
            "run_id",
            "freelancer_user_id",
            name="uq_recommendation_predictions_run_freelancer",
        ),
        sa.UniqueConstraint("run_id", "rank", name="uq_recommendation_predictions_run_rank"),
    )
    op.create_index(
        "ix_recommendation_predictions_run_id",
        "recommendation_predictions",
        ["run_id"],
    )
    op.create_index(
        "ix_recommendation_predictions_freelancer_user_id",
        "recommendation_predictions",
        ["freelancer_user_id"],
    )

    op.create_table(
        "recommendation_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("client_event_id", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('IMPRESSION', 'PROFILE_VIEW')",
            name="ck_recommendation_events_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["recommendation_runs.id"],
            name="fk_recommendation_events_run_id_recommendation_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["freelancer_user_id"],
            ["users.id"],
            name="fk_recommendation_events_freelancer_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_recommendation_events_actor_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recommendation_events"),
        sa.UniqueConstraint(
            "actor_user_id",
            "client_event_id",
            name="uq_recommendation_events_actor_client_event",
        ),
    )
    op.create_index("ix_recommendation_events_run_id", "recommendation_events", ["run_id"])
    op.create_index(
        "ix_recommendation_events_freelancer_user_id",
        "recommendation_events",
        ["freelancer_user_id"],
    )

    op.create_table(
        "risk_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_user_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("feature_version", sa.String(length=80), nullable=False),
        sa.Column("text_hash", sa.String(length=64), nullable=False),
        sa.Column("risk_score_basis_points", sa.Integer(), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("signals_json", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "risk_score_basis_points >= 0 AND risk_score_basis_points <= 10000",
            name="ck_risk_assessments_score_range",
        ),
        sa.CheckConstraint(
            "review_status IN ('NOT_REQUIRED', 'PENDING', 'CLEARED', 'ESCALATED')",
            name="ck_risk_assessments_review_status",
        ),
        sa.CheckConstraint(
            "(review_status IN ('NOT_REQUIRED', 'PENDING') AND reviewer_user_id IS NULL "
            "AND reviewed_at IS NULL) OR "
            "(review_status IN ('CLEARED', 'ESCALATED') AND reviewer_user_id IS NOT NULL "
            "AND reviewed_at IS NOT NULL)",
            name="ck_risk_assessments_review_metadata",
        ),
        sa.ForeignKeyConstraint(
            ["subject_user_id"],
            ["users.id"],
            name="fk_risk_assessments_subject_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            name="fk_risk_assessments_requested_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            name="fk_risk_assessments_reviewer_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_risk_assessments"),
    )
    op.create_index("ix_risk_assessments_subject_user_id", "risk_assessments", ["subject_user_id"])
    op.create_index("ix_risk_assessments_text_hash", "risk_assessments", ["text_hash"])


def downgrade() -> None:
    op.drop_index("ix_risk_assessments_text_hash", table_name="risk_assessments")
    op.drop_index("ix_risk_assessments_subject_user_id", table_name="risk_assessments")
    op.drop_table("risk_assessments")
    op.drop_index(
        "ix_recommendation_events_freelancer_user_id",
        table_name="recommendation_events",
    )
    op.drop_index("ix_recommendation_events_run_id", table_name="recommendation_events")
    op.drop_table("recommendation_events")
    op.drop_index(
        "ix_recommendation_predictions_freelancer_user_id",
        table_name="recommendation_predictions",
    )
    op.drop_index(
        "ix_recommendation_predictions_run_id",
        table_name="recommendation_predictions",
    )
    op.drop_table("recommendation_predictions")
    op.drop_index(
        "ix_recommendation_runs_employer_user_id",
        table_name="recommendation_runs",
    )
    op.drop_index("ix_recommendation_runs_project_id", table_name="recommendation_runs")
    op.drop_table("recommendation_runs")
    op.drop_index("uq_ml_model_versions_active_name", table_name="ml_model_versions")
    op.drop_index("ix_ml_model_versions_name", table_name="ml_model_versions")
    op.drop_table("ml_model_versions")
