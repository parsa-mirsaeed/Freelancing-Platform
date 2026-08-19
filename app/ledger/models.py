from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class LedgerAccount(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "ledger_accounts"
    __table_args__ = (
        CheckConstraint(
            "account_type IN ('PROVIDER_CLEARING', 'MILESTONE_ESCROW', 'FREELANCER_WALLET', "
            "'PLATFORM_COMMISSION')",
            name="ck_ledger_accounts_type",
        ),
        UniqueConstraint("account_key", name="uq_ledger_accounts_account_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    account_key: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="RESTRICT"), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    entries: Mapped[list[LedgerEntry]] = relationship(back_populates="account", lazy="selectin")


class JournalTransaction(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "journal_transactions"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('MILESTONE_FUND', 'MILESTONE_RELEASE', 'MILESTONE_REFUND', "
            "'DISPUTE_RESOLUTION', 'PAYOUT', 'REVERSAL')",
            name="ck_journal_transactions_operation",
        ),
        UniqueConstraint(
            "reference_type",
            "reference_id",
            "operation",
            name="uq_journal_transactions_reference_operation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("journal_transactions.id", ondelete="RESTRICT"), nullable=True
    )
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    entries: Mapped[list[LedgerEntry]] = relationship(
        back_populates="journal",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="LedgerEntry.id",
    )


class LedgerEntry(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_ledger_entries_amount_positive"),
        CheckConstraint("direction IN ('DEBIT', 'CREDIT')", name="ck_ledger_entries_direction"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    journal_transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("journal_transactions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ledger_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ledger_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(6), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    journal: Mapped[JournalTransaction] = relationship(back_populates="entries")
    account: Mapped[LedgerAccount] = relationship(back_populates="entries")


def _reject_financial_mutation(
    _mapper: object, _connection: object, _target: JournalTransaction | LedgerEntry
) -> None:
    raise ValueError("Committed ledger journals and entries are immutable; post a reversal")


event.listen(JournalTransaction, "before_update", _reject_financial_mutation)
event.listen(JournalTransaction, "before_delete", _reject_financial_mutation)
event.listen(LedgerEntry, "before_update", _reject_financial_mutation)
event.listen(LedgerEntry, "before_delete", _reject_financial_mutation)
