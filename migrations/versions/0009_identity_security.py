"""identity MFA, device tracking, and account risk controls

Revision ID: 0009_identity_security
Revises: 0008_ai_baseline
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_identity_security"
down_revision: str | None = "0008_ai_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("failed_login_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("mfa_seed", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "user_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint_hash", sa.String(length=64), nullable=False),
        sa.Column("user_agent_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_devices_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_devices"),
        sa.UniqueConstraint(
            "user_id", "fingerprint_hash", name="uq_user_devices_user_fingerprint"
        ),
    )
    op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"])

    op.create_table(
        "user_verifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_verifications_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_verifications"),
        sa.UniqueConstraint("token_hash", name="uq_user_verifications_token_hash"),
    )
    op.create_index("ix_user_verifications_user_id", "user_verifications", ["user_id"])
    op.create_index("ix_user_verifications_kind", "user_verifications", ["kind"])

    op.add_column("user_sessions", sa.Column("device_id", sa.Uuid(), nullable=True))
    op.add_column("user_sessions", sa.Column("ip_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "user_sessions", sa.Column("user_agent_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "user_sessions", sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "user_sessions",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_user_sessions_device_id_user_devices",
        "user_sessions",
        "user_devices",
        ["device_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_user_sessions_device_id", "user_sessions", ["device_id"])


def downgrade() -> None:
    op.drop_index("ix_user_sessions_device_id", table_name="user_sessions")
    op.drop_constraint(
        "fk_user_sessions_device_id_user_devices", "user_sessions", type_="foreignkey"
    )
    op.drop_column("user_sessions", "last_seen_at")
    op.drop_column("user_sessions", "mfa_verified_at")
    op.drop_column("user_sessions", "user_agent_hash")
    op.drop_column("user_sessions", "ip_hash")
    op.drop_column("user_sessions", "device_id")

    op.drop_index("ix_user_verifications_kind", table_name="user_verifications")
    op.drop_index("ix_user_verifications_user_id", table_name="user_verifications")
    op.drop_table("user_verifications")

    op.drop_index("ix_user_devices_user_id", table_name="user_devices")
    op.drop_table("user_devices")

    op.drop_column("users", "mfa_enabled_at")
    op.drop_column("users", "mfa_seed")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
