from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db


class PayoutProviderAccount(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "payout_provider_accounts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')",
            name="ck_payout_provider_accounts_status",
        ),
        UniqueConstraint(
            "freelancer_user_id",
            "provider",
            name="uq_payout_provider_accounts_user_provider",
        ),
        UniqueConstraint(
            "provider",
            "external_account_reference",
            name="uq_payout_provider_accounts_provider_reference",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    freelancer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    external_account_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class Payout(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "payouts"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_payouts_amount_positive"),
        CheckConstraint("status IN ('PENDING', 'SUCCEEDED', 'FAILED')", name="ck_payouts_status"),
        UniqueConstraint("provider", "provider_reference", name="uq_payouts_provider_reference"),
        UniqueConstraint("journal_transaction_id", name="uq_payouts_journal_transaction_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    freelancer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    idempotency_key_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("financial_idempotency_keys.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    journal_transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("journal_transactions.id", ondelete="RESTRICT"), nullable=False
    )
    reversal_journal_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("journal_transactions.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_destination_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
