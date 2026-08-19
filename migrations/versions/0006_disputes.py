"""dispute resolution and immutable decisions

Revision ID: 0006_disputes
Revises: 0005_communication
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_disputes"
down_revision: str | None = "0005_communication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_journal_transactions_operation",
        "journal_transactions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_journal_transactions_operation",
        "journal_transactions",
        "operation IN ('MILESTONE_FUND', 'MILESTONE_RELEASE', 'MILESTONE_REFUND', "
        "'DISPUTE_RESOLUTION', 'PAYOUT', 'REVERSAL')",
    )
    op.create_table(
        "disputes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("milestone_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("opened_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('OPEN', 'EVIDENCE_COLLECTION', 'UNDER_REVIEW', "
            "'NEED_MORE_INFO', 'RESOLVED')",
            name="ck_disputes_status",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            name="fk_disputes_contract_id_contracts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"],
            ["milestones.id"],
            name="fk_disputes_milestone_id_milestones",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opened_by_user_id"],
            ["users.id"],
            name="fk_disputes_opened_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_disputes"),
        sa.UniqueConstraint("milestone_id", name="uq_disputes_milestone_id"),
    )
    op.create_index("ix_disputes_milestone_id", "disputes", ["milestone_id"])
    op.create_index("ix_disputes_contract_id", "disputes", ["contract_id"])
    op.create_table(
        "dispute_parties",
        sa.Column("dispute_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.CheckConstraint(
            "role IN ('EMPLOYER', 'FREELANCER')", name="ck_dispute_parties_role"
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"],
            ["disputes.id"],
            name="fk_dispute_parties_dispute_id_disputes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_dispute_parties_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("dispute_id", "user_id", name="pk_dispute_parties"),
    )
    op.create_table(
        "dispute_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dispute_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["dispute_id"],
            ["disputes.id"],
            name="fk_dispute_evidence_dispute_id_disputes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["file_objects.id"],
            name="fk_dispute_evidence_file_id_file_objects",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            name="fk_dispute_evidence_submitted_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dispute_evidence"),
        sa.UniqueConstraint(
            "dispute_id", "file_id", name="uq_dispute_evidence_dispute_file"
        ),
    )
    op.create_index("ix_dispute_evidence_dispute_id", "dispute_evidence", ["dispute_id"])
    op.create_table(
        "dispute_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dispute_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=False),
        sa.Column("after_state", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_dispute_events_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"],
            ["disputes.id"],
            name="fk_dispute_events_dispute_id_disputes",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dispute_events"),
    )
    op.create_index("ix_dispute_events_dispute_id", "dispute_events", ["dispute_id"])
    op.create_table(
        "dispute_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dispute_id", sa.Uuid(), nullable=False),
        sa.Column("administrator_user_id", sa.Uuid(), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("freelancer_award_minor", sa.BigInteger(), nullable=False),
        sa.Column("freelancer_net_minor", sa.BigInteger(), nullable=False),
        sa.Column("client_refund_minor", sa.BigInteger(), nullable=False),
        sa.Column("commission_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("journal_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("refund_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('RELEASE_TO_FREELANCER', 'REFUND_CLIENT', 'SPLIT')",
            name="ck_dispute_decisions_outcome",
        ),
        sa.CheckConstraint(
            "freelancer_award_minor >= 0 AND freelancer_net_minor >= 0 "
            "AND client_refund_minor >= 0 AND commission_minor >= 0",
            name="ck_dispute_decisions_amounts_nonnegative",
        ),
        sa.CheckConstraint(
            "freelancer_award_minor = freelancer_net_minor + commission_minor",
            name="ck_dispute_decisions_freelancer_breakdown",
        ),
        sa.ForeignKeyConstraint(
            ["administrator_user_id"],
            ["users.id"],
            name="fk_dispute_decisions_administrator_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dispute_id"],
            ["disputes.id"],
            name="fk_dispute_decisions_dispute_id_disputes",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["journal_transaction_id"],
            ["journal_transactions.id"],
            name=op.f("fk_dispute_decisions_journal_transaction_id_journal_transactions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["refund_id"],
            ["refunds.id"],
            name="fk_dispute_decisions_refund_id_refunds",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dispute_decisions"),
        sa.UniqueConstraint("dispute_id", name="uq_dispute_decisions_dispute_id"),
        sa.UniqueConstraint(
            "journal_transaction_id", name="uq_dispute_decisions_journal_transaction_id"
        ),
        sa.UniqueConstraint("refund_id", name="uq_dispute_decisions_refund_id"),
    )


def downgrade() -> None:
    op.drop_table("dispute_decisions")
    op.drop_index("ix_dispute_events_dispute_id", table_name="dispute_events")
    op.drop_table("dispute_events")
    op.drop_index("ix_dispute_evidence_dispute_id", table_name="dispute_evidence")
    op.drop_table("dispute_evidence")
    op.drop_table("dispute_parties")
    op.drop_index("ix_disputes_contract_id", table_name="disputes")
    op.drop_index("ix_disputes_milestone_id", table_name="disputes")
    op.drop_table("disputes")
    op.drop_constraint(
        "ck_journal_transactions_operation",
        "journal_transactions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_journal_transactions_operation",
        "journal_transactions",
        "operation IN ('MILESTONE_FUND', 'MILESTONE_RELEASE', 'MILESTONE_REFUND', "
        "'PAYOUT', 'REVERSAL')",
    )
