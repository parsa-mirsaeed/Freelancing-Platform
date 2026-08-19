"""one-to-one WebRTC call sessions

Revision ID: 0007_calls
Revises: 0006_disputes
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_calls"
down_revision: str | None = "0006_disputes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "call_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("caller_user_id", sa.Uuid(), nullable=False),
        sa.Column("callee_user_id", sa.Uuid(), nullable=False),
        sa.Column("client_call_id", sa.String(length=80), nullable=False),
        sa.Column("call_type", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "call_type IN ('VOICE', 'VIDEO')",
            name="ck_call_sessions_call_type",
        ),
        sa.CheckConstraint(
            "status IN ('INVITED', 'ACTIVE', 'ENDED')",
            name="ck_call_sessions_status",
        ),
        sa.CheckConstraint(
            "caller_user_id <> callee_user_id",
            name="ck_call_sessions_distinct_parties",
        ),
        sa.CheckConstraint(
            "status != 'INVITED' OR (accepted_at IS NULL AND ended_at IS NULL)",
            name="ck_call_sessions_invited_timestamps",
        ),
        sa.CheckConstraint(
            "status != 'ACTIVE' OR (accepted_at IS NOT NULL AND ended_at IS NULL)",
            name="ck_call_sessions_active_timestamps",
        ),
        sa.CheckConstraint(
            "status != 'ENDED' OR ended_at IS NOT NULL",
            name="ck_call_sessions_ended_timestamp",
        ),
        sa.CheckConstraint(
            "ended_by_user_id IS NULL OR ended_by_user_id = caller_user_id "
            "OR ended_by_user_id = callee_user_id",
            name="ck_call_sessions_ended_by_party",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_call_sessions_conversation_id_conversations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["caller_user_id"],
            ["users.id"],
            name="fk_call_sessions_caller_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["callee_user_id"],
            ["users.id"],
            name="fk_call_sessions_callee_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ended_by_user_id"],
            ["users.id"],
            name="fk_call_sessions_ended_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_call_sessions"),
        sa.UniqueConstraint(
            "caller_user_id",
            "client_call_id",
            name="uq_call_sessions_caller_client_call_id",
        ),
    )
    op.create_index(
        "ix_call_sessions_conversation_id",
        "call_sessions",
        ["conversation_id"],
    )
    op.create_index(
        "uq_call_sessions_live_conversation",
        "call_sessions",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('INVITED', 'ACTIVE')"),
        sqlite_where=sa.text("status IN ('INVITED', 'ACTIVE')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_call_sessions_live_conversation",
        table_name="call_sessions",
    )
    op.drop_index(
        "ix_call_sessions_conversation_id",
        table_name="call_sessions",
    )
    op.drop_table("call_sessions")
