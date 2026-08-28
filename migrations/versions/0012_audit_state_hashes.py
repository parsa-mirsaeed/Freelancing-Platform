"""add audit state hashes

Revision ID: 0012_audit_state_hashes
Revises: 0011_payout_provider_accounts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_audit_state_hashes"
down_revision: str | None = "0011_payout_provider_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Expand-only for rolling deploy compatibility and historical integrity.
    # Existing audit rows remain null because their original before/after state
    # cannot be reconstructed without inventing evidence. New application code
    # writes hashes whenever a real state snapshot is available.
    op.add_column(
        "audit_events",
        sa.Column("previous_state_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("new_state_hash", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_audit_events_previous_state_hash_length",
        "audit_events",
        "previous_state_hash IS NULL OR length(previous_state_hash) = 64",
    )
    op.create_check_constraint(
        "ck_audit_events_new_state_hash_length",
        "audit_events",
        "new_state_hash IS NULL OR length(new_state_hash) = 64",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_audit_events_new_state_hash_length",
        "audit_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_audit_events_previous_state_hash_length",
        "audit_events",
        type_="check",
    )
    op.drop_column("audit_events", "new_state_hash")
    op.drop_column("audit_events", "previous_state_hash")
