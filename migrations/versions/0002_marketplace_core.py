"""marketplace core tables

Revision ID: 0002_marketplace_core
Revises: 0001_foundation_identity
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_marketplace_core"
down_revision: str | None = "0001_foundation_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_skills"),
        sa.UniqueConstraint("name", name="uq_skills_name"),
        sa.UniqueConstraint("slug", name="uq_skills_slug"),
    )
    op.create_table(
        "freelancer_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("hourly_rate_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("accepting_work", sa.Boolean(), nullable=False),
        sa.Column("languages", sa.JSON(), nullable=False),
        sa.Column("projection_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(hourly_rate_minor IS NULL AND currency IS NULL) OR "
            "(hourly_rate_minor IS NOT NULL AND hourly_rate_minor >= 0 "
            "AND currency IS NOT NULL)",
            name="ck_freelancer_profiles_hourly_rate_currency",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_freelancer_profiles_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_freelancer_profiles"),
        sa.UniqueConstraint("user_id", name="uq_freelancer_profiles_user_id"),
    )
    op.create_table(
        "freelancer_skills",
        sa.Column("freelancer_profile_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["freelancer_profile_id"],
            ["freelancer_profiles.id"],
            name="fk_freelancer_skills_freelancer_profile_id_freelancer_profiles",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_freelancer_skills_skill_id_skills", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("freelancer_profile_id", "skill_id", name="pk_freelancer_skills"),
    )
    op.create_table(
        "availability_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_profile_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_availability_rules_weekday_range"),
        sa.CheckConstraint("start_time < end_time", name="ck_availability_rules_time_range"),
        sa.ForeignKeyConstraint(
            ["freelancer_profile_id"],
            ["freelancer_profiles.id"],
            name="fk_availability_rules_freelancer_profile_id_freelancer_profiles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_availability_rules"),
        sa.UniqueConstraint(
            "freelancer_profile_id",
            "weekday",
            "start_time",
            "end_time",
            name="uq_availability_rule_slot",
        ),
    )
    op.create_index(
        "ix_availability_rules_freelancer_profile_id",
        "availability_rules",
        ["freelancer_profile_id"],
        unique=False,
    )
    op.create_table(
        "availability_exceptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_profile_id", sa.Uuid(), nullable=False),
        sa.Column("exception_date", sa.Date(), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("reason", sa.String(length=240), nullable=True),
        sa.CheckConstraint(
            "(start_time IS NULL AND end_time IS NULL) OR "
            "(start_time IS NOT NULL AND end_time IS NOT NULL AND start_time < end_time)",
            name="ck_availability_exceptions_optional_time_range",
        ),
        sa.ForeignKeyConstraint(
            ["freelancer_profile_id"],
            ["freelancer_profiles.id"],
            name=op.f("fk_availability_exceptions_freelancer_profile_id_freelancer_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_availability_exceptions"),
        sa.UniqueConstraint(
            "freelancer_profile_id", "exception_date", name="uq_availability_exception_date"
        ),
    )
    op.create_index(
        "ix_availability_exceptions_freelancer_profile_id",
        "availability_exceptions",
        ["freelancer_profile_id"],
        unique=False,
    )
    op.create_table(
        "portfolio_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_profile_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("external_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["freelancer_profile_id"],
            ["freelancer_profiles.id"],
            name="fk_portfolio_items_freelancer_profile_id_freelancer_profiles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_portfolio_items"),
    )
    op.create_index(
        "ix_portfolio_items_freelancer_profile_id",
        "portfolio_items",
        ["freelancer_profile_id"],
        unique=False,
    )
    op.create_table(
        "portfolio_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_item_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("scan_status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("file_size_bytes >= 0", name="ck_portfolio_files_file_size_nonnegative"),
        sa.CheckConstraint(
            "scan_status IN ('QUARANTINED', 'SCANNING', 'SAFE', 'REJECTED')",
            name="ck_portfolio_files_scan_status",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_item_id"],
            ["portfolio_items.id"],
            name="fk_portfolio_files_portfolio_item_id_portfolio_items",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_portfolio_files"),
        sa.UniqueConstraint("object_key", name="uq_portfolio_files_object_key"),
    )
    op.create_index(
        "ix_portfolio_files_portfolio_item_id",
        "portfolio_files",
        ["portfolio_item_id"],
        unique=False,
    )
    op.create_table(
        "gigs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_profile_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["freelancer_profile_id"],
            ["freelancer_profiles.id"],
            name="fk_gigs_freelancer_profile_id_freelancer_profiles",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_gigs"),
    )
    op.create_index("ix_gigs_freelancer_profile_id", "gigs", ["freelancer_profile_id"], unique=False)
    op.create_table(
        "gig_packages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("gig_id", sa.Uuid(), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("delivery_days", sa.Integer(), nullable=False),
        sa.Column("revisions", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.CheckConstraint("tier IN ('BASIC', 'STANDARD', 'PREMIUM')", name="ck_gig_packages_tier"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_gig_packages_amount_nonnegative"),
        sa.CheckConstraint("delivery_days >= 1", name="ck_gig_packages_delivery_positive"),
        sa.CheckConstraint("revisions >= 0", name="ck_gig_packages_revisions_nonnegative"),
        sa.ForeignKeyConstraint(
            ["gig_id"], ["gigs.id"], name="fk_gig_packages_gig_id_gigs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_gig_packages"),
        sa.UniqueConstraint("gig_id", "tier", name="uq_gig_package_tier"),
    )
    op.create_index("ix_gig_packages_gig_id", "gig_packages", ["gig_id"], unique=False)
    op.create_table(
        "gig_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("gig_id", sa.Uuid(), nullable=False),
        sa.Column("prompt", sa.String(length=500), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["gig_id"], ["gigs.id"], name="fk_gig_requirements_gig_id_gigs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_gig_requirements"),
    )
    op.create_index("ix_gig_requirements_gig_id", "gig_requirements", ["gig_id"], unique=False)
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employer_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("budget_min_minor", sa.BigInteger(), nullable=True),
        sa.Column("budget_max_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED', 'CANCELLED')", name="ck_projects_status"),
        sa.CheckConstraint(
            "(budget_min_minor IS NULL AND budget_max_minor IS NULL AND currency IS NULL) OR "
            "(budget_min_minor IS NOT NULL AND budget_max_minor IS NOT NULL "
            "AND currency IS NOT NULL AND budget_min_minor >= 0 "
            "AND budget_max_minor >= budget_min_minor)",
            name="ck_projects_budget_range",
        ),
        sa.ForeignKeyConstraint(
            ["employer_user_id"],
            ["users.id"],
            name="fk_projects_employer_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
    )
    op.create_index("ix_projects_employer_user_id", "projects", ["employer_user_id"], unique=False)
    op.create_index("ix_projects_status", "projects", ["status"], unique=False)
    op.create_table(
        "project_skills",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_project_skills_project_id_projects", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name="fk_project_skills_skill_id_skills", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("project_id", "skill_id", name="pk_project_skills"),
    )
    op.create_table(
        "project_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("scan_status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("file_size_bytes >= 0", name="ck_project_attachments_file_size_nonnegative"),
        sa.CheckConstraint(
            "scan_status IN ('QUARANTINED', 'SCANNING', 'SAFE', 'REJECTED')",
            name="ck_project_attachments_scan_status",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_attachments_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_attachments"),
        sa.UniqueConstraint("object_key", name="uq_project_attachments_object_key"),
    )
    op.create_index(
        "ix_project_attachments_project_id",
        "project_attachments",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "project_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_user_id", sa.Uuid(), nullable=False),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'DECLINED', 'CANCELLED')",
            name="ck_project_invites_status",
        ),
        sa.ForeignKeyConstraint(
            ["freelancer_user_id"],
            ["users.id"],
            name="fk_project_invites_freelancer_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            name="fk_project_invites_invited_by_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_invites_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_invites"),
        sa.UniqueConstraint("project_id", "freelancer_user_id", name="uq_project_invite_freelancer"),
    )
    op.create_index(
        "ix_project_invites_freelancer_user_id",
        "project_invites",
        ["freelancer_user_id"],
        unique=False,
    )
    op.create_index("ix_project_invites_project_id", "project_invites", ["project_id"], unique=False)
    op.create_table(
        "proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'SUBMITTED', 'UNDER_NEGOTIATION', 'WITHDRAWN', 'REJECTED', 'ACCEPTED')",
            name="ck_proposals_status",
        ),
        sa.CheckConstraint("current_version >= 1", name="ck_proposals_current_version_positive"),
        sa.ForeignKeyConstraint(
            ["freelancer_user_id"],
            ["users.id"],
            name="fk_proposals_freelancer_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_proposals_project_id_projects", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proposals"),
        sa.UniqueConstraint("project_id", "freelancer_user_id", name="uq_proposal_project_freelancer"),
    )
    op.create_index("ix_proposals_freelancer_user_id", "proposals", ["freelancer_user_id"], unique=False)
    op.create_index("ix_proposals_project_id", "proposals", ["project_id"], unique=False)
    op.create_index("ix_proposals_status", "proposals", ["status"], unique=False)
    op.create_index(
        "uq_proposals_one_accepted_per_project",
        "proposals",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACCEPTED'"),
        sqlite_where=sa.text("status = 'ACCEPTED'"),
    )
    op.create_table(
        "proposal_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("delivery_days", sa.Integer(), nullable=False),
        sa.Column("cover_letter", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version_number >= 1", name="ck_proposal_versions_version_positive"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_proposal_versions_amount_nonnegative"),
        sa.CheckConstraint("delivery_days >= 1", name="ck_proposal_versions_delivery_positive"),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["proposals.id"],
            name="fk_proposal_versions_proposal_id_proposals",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proposal_versions"),
        sa.UniqueConstraint("proposal_id", "version_number", name="uq_proposal_version_number"),
    )
    op.create_index("ix_proposal_versions_proposal_id", "proposal_versions", ["proposal_id"], unique=False)
    op.create_table(
        "proposal_milestones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_version_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("delivery_days", sa.Integer(), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_proposal_milestones_sequence_positive"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_proposal_milestones_amount_nonnegative"),
        sa.CheckConstraint("delivery_days >= 1", name="ck_proposal_milestones_delivery_positive"),
        sa.ForeignKeyConstraint(
            ["proposal_version_id"],
            ["proposal_versions.id"],
            name="fk_proposal_milestones_proposal_version_id_proposal_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proposal_milestones"),
        sa.UniqueConstraint(
            "proposal_version_id", "sequence", name="uq_proposal_milestone_sequence"
        ),
    )
    op.create_index(
        "ix_proposal_milestones_proposal_version_id",
        "proposal_milestones",
        ["proposal_version_id"],
        unique=False,
    )
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating >= 1 AND rating <= 5", name="ck_reviews_rating_range"),
        sa.ForeignKeyConstraint(
            ["freelancer_user_id"],
            ["users.id"],
            name="fk_reviews_freelancer_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_reviews_project_id_projects", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            name="fk_reviews_reviewer_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reviews"),
        sa.UniqueConstraint(
            "project_id", "reviewer_user_id", "freelancer_user_id", name="uq_review_project_parties"
        ),
    )
    op.create_index("ix_reviews_freelancer_user_id", "reviews", ["freelancer_user_id"], unique=False)
    op.create_index("ix_reviews_project_id", "reviews", ["project_id"], unique=False)
    op.create_index("ix_reviews_reviewer_user_id", "reviews", ["reviewer_user_id"], unique=False)
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.String(length=120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
    )
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"], unique=False)
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_outbox_events_event_type", table_name="outbox_events")
    op.drop_index("ix_outbox_events_aggregate_id", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.drop_index("ix_reviews_reviewer_user_id", table_name="reviews")
    op.drop_index("ix_reviews_project_id", table_name="reviews")
    op.drop_index("ix_reviews_freelancer_user_id", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_proposal_milestones_proposal_version_id", table_name="proposal_milestones")
    op.drop_table("proposal_milestones")
    op.drop_index("ix_proposal_versions_proposal_id", table_name="proposal_versions")
    op.drop_table("proposal_versions")
    op.drop_index("uq_proposals_one_accepted_per_project", table_name="proposals")
    op.drop_index("ix_proposals_status", table_name="proposals")
    op.drop_index("ix_proposals_project_id", table_name="proposals")
    op.drop_index("ix_proposals_freelancer_user_id", table_name="proposals")
    op.drop_table("proposals")
    op.drop_index("ix_project_invites_project_id", table_name="project_invites")
    op.drop_index("ix_project_invites_freelancer_user_id", table_name="project_invites")
    op.drop_table("project_invites")
    op.drop_index("ix_project_attachments_project_id", table_name="project_attachments")
    op.drop_table("project_attachments")
    op.drop_table("project_skills")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_index("ix_projects_employer_user_id", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_gig_requirements_gig_id", table_name="gig_requirements")
    op.drop_table("gig_requirements")
    op.drop_index("ix_gig_packages_gig_id", table_name="gig_packages")
    op.drop_table("gig_packages")
    op.drop_index("ix_gigs_freelancer_profile_id", table_name="gigs")
    op.drop_table("gigs")
    op.drop_index("ix_portfolio_files_portfolio_item_id", table_name="portfolio_files")
    op.drop_table("portfolio_files")
    op.drop_index("ix_portfolio_items_freelancer_profile_id", table_name="portfolio_items")
    op.drop_table("portfolio_items")
    op.drop_index(
        "ix_availability_exceptions_freelancer_profile_id", table_name="availability_exceptions"
    )
    op.drop_table("availability_exceptions")
    op.drop_index("ix_availability_rules_freelancer_profile_id", table_name="availability_rules")
    op.drop_table("availability_rules")
    op.drop_table("freelancer_skills")
    op.drop_table("freelancer_profiles")
    op.drop_table("skills")
