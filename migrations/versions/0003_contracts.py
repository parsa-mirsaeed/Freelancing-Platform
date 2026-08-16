"""contract snapshots, signatures, and milestone progress

Revision ID: 0003_contracts
Revises: 0002_marketplace_core
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_contracts"
down_revision: str | None = "0002_marketplace_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_proposal_id", sa.Uuid(), nullable=False),
        sa.Column("employer_user_id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING_SIGNATURES', 'ACTIVE', 'CANCELLED')",
            name="ck_contracts_status",
        ),
        sa.CheckConstraint(
            "current_version >= 1", name="ck_contracts_current_version_positive"
        ),
        sa.ForeignKeyConstraint(
            ["accepted_proposal_id"],
            ["proposals.id"],
            name="fk_contracts_accepted_proposal_id_proposals",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["employer_user_id"],
            ["users.id"],
            name="fk_contracts_employer_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["freelancer_user_id"],
            ["users.id"],
            name="fk_contracts_freelancer_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_contracts_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contracts"),
        sa.UniqueConstraint("accepted_proposal_id", name="uq_contracts_accepted_proposal_id"),
        sa.UniqueConstraint("project_id", name="uq_contracts_project_id"),
    )
    op.create_table(
        "contract_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version_number >= 1", name="ck_contract_versions_version_positive"
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            name="fk_contract_versions_contract_id_contracts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contract_versions"),
        sa.UniqueConstraint("contract_id", "version_number", name="uq_contract_version_number"),
    )
    op.create_table(
        "contract_parties",
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("required_signature", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "role IN ('EMPLOYER', 'FREELANCER')", name="ck_contract_parties_role"
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            name="fk_contract_parties_contract_id_contracts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_contract_parties_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("contract_id", "user_id", name="pk_contract_parties"),
    )
    op.create_table(
        "contract_signatures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contract_version_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_metadata", sa.JSON(), nullable=False),
        sa.Column("risk_metadata", sa.JSON(), nullable=False),
        sa.Column("signature_provider_reference", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["contract_version_id"],
            ["contract_versions.id"],
            name="fk_contract_signatures_contract_version_id_contract_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_contract_signatures_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contract_signatures"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key_hash", name="uq_contract_signature_idempotency"
        ),
        sa.UniqueConstraint(
            "contract_version_id", "user_id", name="uq_contract_signature_version_user"
        ),
    )
    op.create_table(
        "milestones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contract_version_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("delivery_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_milestones_sequence_positive"),
        sa.CheckConstraint("amount_minor >= 0", name="ck_milestones_amount_nonnegative"),
        sa.CheckConstraint("delivery_days >= 1", name="ck_milestones_delivery_positive"),
        sa.CheckConstraint(
            "status IN ('CREATED', 'FUNDED', 'IN_PROGRESS', 'SUBMITTED', "
            "'CHANGES_REQUESTED', 'DISPUTED', 'APPROVED', 'RELEASE_PENDING', 'RELEASED')",
            name="ck_milestones_status",
        ),
        sa.ForeignKeyConstraint(
            ["contract_version_id"],
            ["contract_versions.id"],
            name="fk_milestones_contract_version_id_contract_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_milestones"),
        sa.UniqueConstraint(
            "contract_version_id", "sequence", name="uq_milestone_contract_sequence"
        ),
    )
    op.create_table(
        "milestone_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("milestone_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("from_status", sa.String(length=24), nullable=False),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name="fk_milestone_events_actor_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"],
            ["milestones.id"],
            name="fk_milestone_events_milestone_id_milestones",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_milestone_events"),
    )
    op.create_index(
        "ix_milestone_events_milestone_id", "milestone_events", ["milestone_id"], unique=False
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_immutable_contract_row_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'immutable contract record cannot be updated or deleted';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table in ("contract_versions", "contract_signatures", "milestone_events"):
            op.execute(
                f"""
                CREATE TRIGGER trg_{table}_immutable
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION reject_immutable_contract_row_mutation()
                """
            )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in ("milestone_events", "contract_signatures", "contract_versions"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
        op.execute("DROP FUNCTION IF EXISTS reject_immutable_contract_row_mutation()")

    op.drop_index("ix_milestone_events_milestone_id", table_name="milestone_events")
    op.drop_table("milestone_events")
    op.drop_table("milestones")
    op.drop_table("contract_signatures")
    op.drop_table("contract_parties")
    op.drop_table("contract_versions")
    op.drop_table("contracts")
