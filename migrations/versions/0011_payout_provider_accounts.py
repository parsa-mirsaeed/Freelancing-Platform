"""add payout provider account mappings and destination snapshots

Revision ID: 0011_payout_provider_accounts
Revises: 0010_pii_encryption
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_payout_provider_accounts"
down_revision: str | None = "0010_pii_encryption"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "payout_provider_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_account_reference", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')",
            name="ck_payout_provider_accounts_status",
        ),
        sa.ForeignKeyConstraint(
            ["freelancer_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "freelancer_user_id",
            "provider",
            name="uq_payout_provider_accounts_user_provider",
        ),
        sa.UniqueConstraint(
            "provider",
            "external_account_reference",
            name="uq_payout_provider_accounts_provider_reference",
        ),
    )
    op.create_index(
        op.f("ix_payout_provider_accounts_freelancer_user_id"),
        "payout_provider_accounts",
        ["freelancer_user_id"],
        unique=False,
    )

    op.add_column(
        "payouts",
        sa.Column("provider_destination_reference", sa.String(length=255), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE payouts SET provider_destination_reference = CAST(freelancer_user_id AS TEXT) "
            "WHERE provider_destination_reference IS NULL"
        )
    )
    op.alter_column(
        "payouts",
        "provider_destination_reference",
        existing_type=sa.String(length=255),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("payouts", "provider_destination_reference")
    op.drop_index(
        op.f("ix_payout_provider_accounts_freelancer_user_id"),
        table_name="payout_provider_accounts",
    )
    op.drop_table("payout_provider_accounts")
