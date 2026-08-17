"""double-entry money, escrow, refunds, payouts, and reconciliation

Revision ID: 0004_money
Revises: 0003_contracts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_money"
down_revision: str | None = "0003_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_key", sa.String(length=255), nullable=False),
        sa.Column("account_type", sa.String(length=32), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("milestone_id", sa.Uuid(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "account_type IN ('PROVIDER_CLEARING', 'MILESTONE_ESCROW', "
            "'FREELANCER_WALLET', 'PLATFORM_COMMISSION')",
            name="ck_ledger_accounts_type",
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["milestones.id"],
            name="fk_ledger_accounts_milestone_id_milestones", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"],
            name="fk_ledger_accounts_owner_user_id_users", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ledger_accounts"),
        sa.UniqueConstraint("account_key", name="uq_ledger_accounts_account_key"),
    )
    op.create_table(
        "journal_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("reference_type", sa.String(length=40), nullable=False),
        sa.Column("reference_id", sa.String(length=120), nullable=False),
        sa.Column("reversal_of_id", sa.Uuid(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "operation IN ('MILESTONE_FUND', 'MILESTONE_RELEASE', 'MILESTONE_REFUND', "
            "'PAYOUT', 'REVERSAL')",
            name="ck_journal_transactions_operation",
        ),
        sa.ForeignKeyConstraint(
            ["reversal_of_id"], ["journal_transactions.id"],
            name="fk_journal_transactions_reversal_of_id_journal_transactions",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_journal_transactions"),
        sa.UniqueConstraint(
            "reference_type", "reference_id", "operation",
            name="uq_journal_transactions_reference_operation",
        ),
    )
    op.create_table(
        "financial_idempotency_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_financial_idempotency_keys_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_financial_idempotency_keys"),
        sa.UniqueConstraint(
            "user_id", "operation", "key_hash", name="uq_financial_idempotency_scope"
        ),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("journal_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("ledger_account_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=6), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_ledger_entries_amount_positive"),
        sa.CheckConstraint("direction IN ('DEBIT', 'CREDIT')", name="ck_ledger_entries_direction"),
        sa.ForeignKeyConstraint(
            ["journal_transaction_id"], ["journal_transactions.id"],
            name="fk_ledger_entries_journal_transaction_id_journal_transactions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ledger_account_id"], ["ledger_accounts.id"],
            name="fk_ledger_entries_ledger_account_id_ledger_accounts", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ledger_entries"),
    )
    op.create_index(
        "ix_ledger_entries_journal_transaction_id", "ledger_entries",
        ["journal_transaction_id"], unique=False
    )
    op.create_index(
        "ix_ledger_entries_ledger_account_id", "ledger_entries",
        ["ledger_account_id"], unique=False
    )
    op.create_table(
        "payment_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("milestone_id", sa.Uuid(), nullable=False),
        sa.Column("employer_user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("idempotency_key_id", sa.Uuid(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_payment_intents_amount_positive"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CAPTURED', 'FAILED', 'CANCELLED')",
            name="ck_payment_intents_status",
        ),
        sa.ForeignKeyConstraint(
            ["employer_user_id"], ["users.id"],
            name="fk_payment_intents_employer_user_id_users", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["idempotency_key_id"], ["financial_idempotency_keys.id"],
            name=op.f("fk_payment_intents_idempotency_key_id_financial_idempotency_keys"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["milestones.id"],
            name="fk_payment_intents_milestone_id_milestones", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payment_intents"),
        sa.UniqueConstraint("idempotency_key_id", name="uq_payment_intents_idempotency_key_id"),
        sa.UniqueConstraint(
            "provider", "provider_reference", name="uq_payment_intents_provider_reference"
        ),
    )
    op.create_index("ix_payment_intents_milestone_id", "payment_intents", ["milestone_id"])
    op.create_table(
        "milestone_escrows",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("milestone_id", sa.Uuid(), nullable=False),
        sa.Column("escrow_account_id", sa.Uuid(), nullable=False),
        sa.Column("commission_bps", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "commission_bps >= 0 AND commission_bps <= 10000",
            name="ck_milestone_escrows_commission_bps",
        ),
        sa.ForeignKeyConstraint(
            ["escrow_account_id"], ["ledger_accounts.id"],
            name="fk_milestone_escrows_escrow_account_id_ledger_accounts", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["milestones.id"],
            name="fk_milestone_escrows_milestone_id_milestones", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_milestone_escrows"),
        sa.UniqueConstraint("escrow_account_id", name="uq_milestone_escrows_escrow_account_id"),
        sa.UniqueConstraint("milestone_id", name="uq_milestone_escrows_milestone_id"),
    )
    op.create_table(
        "provider_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_provider_events"),
        sa.UniqueConstraint(
            "provider", "external_event_id", name="uq_provider_events_provider_external_id"
        ),
    )
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("checked_count", sa.Integer(), nullable=False),
        sa.Column("discrepancy_count", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'MISMATCH')", name="ck_reconciliation_runs_status"
        ),
        sa.CheckConstraint(
            "checked_count >= 0", name="ck_reconciliation_runs_checked_nonnegative"
        ),
        sa.CheckConstraint(
            "discrepancy_count >= 0", name="ck_reconciliation_runs_discrepancy_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_reconciliation_runs"),
    )
    op.create_table(
        "milestone_fundings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("escrow_id", sa.Uuid(), nullable=False),
        sa.Column("payment_intent_id", sa.Uuid(), nullable=False),
        sa.Column("journal_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_milestone_fundings_amount_positive"),
        sa.ForeignKeyConstraint(
            ["escrow_id"], ["milestone_escrows.id"],
            name="fk_milestone_fundings_escrow_id_milestone_escrows", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["journal_transaction_id"], ["journal_transactions.id"],
            name=op.f("fk_milestone_fundings_journal_transaction_id_journal_transactions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payment_intent_id"], ["payment_intents.id"],
            name="fk_milestone_fundings_payment_intent_id_payment_intents", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_milestone_fundings"),
        sa.UniqueConstraint(
            "journal_transaction_id", name="uq_milestone_fundings_journal_transaction_id"
        ),
        sa.UniqueConstraint("payment_intent_id", name="uq_milestone_fundings_payment_intent_id"),
    )
    op.create_index("ix_milestone_fundings_escrow_id", "milestone_fundings", ["escrow_id"])
    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("milestone_id", sa.Uuid(), nullable=False),
        sa.Column("employer_user_id", sa.Uuid(), nullable=False),
        sa.Column("journal_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_refunds_amount_positive"),
        sa.CheckConstraint("status IN ('PENDING', 'SUCCEEDED', 'FAILED')", name="ck_refunds_status"),
        sa.ForeignKeyConstraint(
            ["employer_user_id"], ["users.id"], name="fk_refunds_employer_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["idempotency_key_id"], ["financial_idempotency_keys.id"],
            name="fk_refunds_idempotency_key_id_financial_idempotency_keys", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["journal_transaction_id"], ["journal_transactions.id"],
            name="fk_refunds_journal_transaction_id_journal_transactions", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["milestone_id"], ["milestones.id"], name="fk_refunds_milestone_id_milestones",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refunds"),
        sa.UniqueConstraint("idempotency_key_id", name="uq_refunds_idempotency_key_id"),
        sa.UniqueConstraint("journal_transaction_id", name="uq_refunds_journal_transaction_id"),
        sa.UniqueConstraint("provider", "provider_reference", name="uq_refunds_provider_reference"),
    )
    op.create_index("ix_refunds_milestone_id", "refunds", ["milestone_id"])
    op.create_table(
        "payouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("freelancer_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key_id", sa.Uuid(), nullable=False),
        sa.Column("journal_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("reversal_journal_transaction_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount_minor > 0", name="ck_payouts_amount_positive"),
        sa.CheckConstraint("status IN ('PENDING', 'SUCCEEDED', 'FAILED')", name="ck_payouts_status"),
        sa.ForeignKeyConstraint(
            ["freelancer_user_id"], ["users.id"], name="fk_payouts_freelancer_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["idempotency_key_id"], ["financial_idempotency_keys.id"],
            name="fk_payouts_idempotency_key_id_financial_idempotency_keys", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["journal_transaction_id"], ["journal_transactions.id"],
            name="fk_payouts_journal_transaction_id_journal_transactions", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reversal_journal_transaction_id"], ["journal_transactions.id"],
            name=op.f("fk_payouts_reversal_journal_transaction_id_journal_transactions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payouts"),
        sa.UniqueConstraint("idempotency_key_id", name="uq_payouts_idempotency_key_id"),
        sa.UniqueConstraint("journal_transaction_id", name="uq_payouts_journal_transaction_id"),
        sa.UniqueConstraint("provider", "provider_reference", name="uq_payouts_provider_reference"),
        sa.UniqueConstraint(
            "reversal_journal_transaction_id", name="uq_payouts_reversal_journal_transaction_id"
        ),
    )
    op.create_index("ix_payouts_freelancer_user_id", "payouts", ["freelancer_user_id"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_immutable_financial_row_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'financial ledger records are append-only; post a reversal';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table in ("journal_transactions", "ledger_entries"):
            op.execute(
                f"""
                CREATE TRIGGER trg_{table}_immutable
                BEFORE UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION reject_immutable_financial_row_mutation()
                """
            )
        op.execute(
            """
            CREATE FUNCTION enforce_balanced_journal()
            RETURNS trigger AS $$
            DECLARE
                journal_id uuid;
                entry_count integer;
                currency_count integer;
                net_amount bigint;
            BEGIN
                IF TG_TABLE_NAME = 'journal_transactions' THEN
                    journal_id := NEW.id;
                ELSE
                    journal_id := NEW.journal_transaction_id;
                END IF;
                SELECT COUNT(*), COUNT(DISTINCT currency),
                    COALESCE(SUM(CASE WHEN direction = 'DEBIT' THEN amount_minor
                                      ELSE -amount_minor END), 0)
                INTO entry_count, currency_count, net_amount
                FROM ledger_entries WHERE journal_transaction_id = journal_id;
                IF entry_count < 2 OR currency_count <> 1 OR net_amount <> 0 THEN
                    RAISE EXCEPTION 'journal % must contain balanced single-currency entries',
                        journal_id;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE CONSTRAINT TRIGGER trg_journal_transactions_balanced
            AFTER INSERT ON journal_transactions
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION enforce_balanced_journal()
            """
        )
        op.execute(
            """
            CREATE CONSTRAINT TRIGGER trg_ledger_entries_balanced
            AFTER INSERT ON ledger_entries
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION enforce_balanced_journal()
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_ledger_entries_balanced ON ledger_entries")
        op.execute(
            "DROP TRIGGER IF EXISTS trg_journal_transactions_balanced ON journal_transactions"
        )
        op.execute("DROP FUNCTION IF EXISTS enforce_balanced_journal()")
        for table in ("ledger_entries", "journal_transactions"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
        op.execute("DROP FUNCTION IF EXISTS reject_immutable_financial_row_mutation()")
    op.drop_index("ix_payouts_freelancer_user_id", table_name="payouts")
    op.drop_table("payouts")
    op.drop_index("ix_refunds_milestone_id", table_name="refunds")
    op.drop_table("refunds")
    op.drop_index("ix_milestone_fundings_escrow_id", table_name="milestone_fundings")
    op.drop_table("milestone_fundings")
    op.drop_table("reconciliation_runs")
    op.drop_table("provider_events")
    op.drop_table("milestone_escrows")
    op.drop_index("ix_payment_intents_milestone_id", table_name="payment_intents")
    op.drop_table("payment_intents")
    op.drop_index("ix_ledger_entries_ledger_account_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_journal_transaction_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_table("financial_idempotency_keys")
    op.drop_table("journal_transactions")
    op.drop_table("ledger_accounts")
