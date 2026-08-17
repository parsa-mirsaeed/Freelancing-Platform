from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class FinancialIdempotencyKey(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "financial_idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "operation", "key_hash", name="uq_financial_idempotency_scope"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class PaymentIntent(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "payment_intents"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_payment_intents_amount_positive"),
        CheckConstraint(
            "status IN ('PENDING', 'CAPTURED', 'FAILED', 'CANCELLED')",
            name="ck_payment_intents_status",
        ),
        UniqueConstraint(
            "provider", "provider_reference", name="uq_payment_intents_provider_reference"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    milestone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    employer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("financial_idempotency_keys.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class MilestoneEscrow(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "milestone_escrows"
    __table_args__ = (
        CheckConstraint(
            "commission_bps >= 0 AND commission_bps <= 10000",
            name="ck_milestone_escrows_commission_bps",
        ),
        UniqueConstraint("milestone_id", name="uq_milestone_escrows_milestone_id"),
        UniqueConstraint("escrow_account_id", name="uq_milestone_escrows_escrow_account_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    milestone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="RESTRICT"), nullable=False
    )
    escrow_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ledger_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    commission_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class MilestoneFunding(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "milestone_fundings"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_milestone_fundings_amount_positive"),
        UniqueConstraint("payment_intent_id", name="uq_milestone_fundings_payment_intent_id"),
        UniqueConstraint(
            "journal_transaction_id", name="uq_milestone_fundings_journal_transaction_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    escrow_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("milestone_escrows.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payment_intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("payment_intents.id", ondelete="RESTRICT"), nullable=False
    )
    journal_transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("journal_transactions.id", ondelete="RESTRICT"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class Refund(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "refunds"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_refunds_amount_positive"),
        CheckConstraint("status IN ('PENDING', 'SUCCEEDED', 'FAILED')", name="ck_refunds_status"),
        UniqueConstraint("provider", "provider_reference", name="uq_refunds_provider_reference"),
        UniqueConstraint("journal_transaction_id", name="uq_refunds_journal_transaction_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    milestone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    employer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    journal_transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("journal_transactions.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("financial_idempotency_keys.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class ProviderEvent(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "provider_events"
    __table_args__ = (
        UniqueConstraint(
            "provider", "external_event_id", name="uq_provider_events_provider_external_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class ReconciliationRun(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('RUNNING', 'SUCCEEDED', 'MISMATCH')",
            name="ck_reconciliation_runs_status",
        ),
        CheckConstraint("checked_count >= 0", name="ck_reconciliation_runs_checked_nonnegative"),
        CheckConstraint(
            "discrepancy_count >= 0", name="ck_reconciliation_runs_discrepancy_nonnegative"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="RUNNING")
    checked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discrepancy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def _reject_processed_provider_event_mutation(
    _mapper: object, _connection: object, target: ProviderEvent
) -> None:
    if target.processed_at is not None:
        raise ValueError("Processed provider events are immutable")


event.listen(ProviderEvent, "before_delete", _reject_processed_provider_event_mutation)
