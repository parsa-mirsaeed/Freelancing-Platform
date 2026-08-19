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
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

DISPUTE_STATES = (
    "OPEN",
    "EVIDENCE_COLLECTION",
    "UNDER_REVIEW",
    "NEED_MORE_INFO",
    "RESOLVED",
)
DISPUTE_OUTCOMES = ("RELEASE_TO_FREELANCER", "REFUND_CLIENT", "SPLIT")


class Dispute(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "disputes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN', 'EVIDENCE_COLLECTION', 'UNDER_REVIEW', "
            "'NEED_MORE_INFO', 'RESOLVED')",
            name="ck_disputes_status",
        ),
        UniqueConstraint("milestone_id", name="uq_disputes_milestone_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    milestone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("contracts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    opened_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parties: Mapped[list[DisputeParty]] = relationship(
        back_populates="dispute",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    evidence: Mapped[list[DisputeEvidence]] = relationship(
        back_populates="dispute",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DisputeEvidence.created_at",
    )
    events: Mapped[list[DisputeEvent]] = relationship(
        back_populates="dispute",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DisputeEvent.created_at",
    )
    decision: Mapped[DisputeDecision | None] = relationship(
        back_populates="dispute",
        cascade="all, delete-orphan",
        lazy="selectin",
        uselist=False,
    )


class DisputeParty(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "dispute_parties"
    __table_args__ = (
        CheckConstraint(
            "role IN ('EMPLOYER', 'FREELANCER')",
            name="ck_dispute_parties_role",
        ),
    )

    dispute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disputes.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    dispute: Mapped[Dispute] = relationship(back_populates="parties")


class DisputeEvidence(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "dispute_evidence"
    __table_args__ = (
        UniqueConstraint(
            "dispute_id",
            "file_id",
            name="uq_dispute_evidence_dispute_file",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dispute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("file_objects.id", ondelete="RESTRICT"), nullable=False
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    dispute: Mapped[Dispute] = relationship(back_populates="evidence")


class DisputeEvent(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "dispute_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dispute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    before_state: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    after_state: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    dispute: Mapped[Dispute] = relationship(back_populates="events")


class DisputeDecision(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "dispute_decisions"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('RELEASE_TO_FREELANCER', 'REFUND_CLIENT', 'SPLIT')",
            name="ck_dispute_decisions_outcome",
        ),
        CheckConstraint(
            "freelancer_award_minor >= 0 AND freelancer_net_minor >= 0 "
            "AND client_refund_minor >= 0 AND commission_minor >= 0",
            name="ck_dispute_decisions_amounts_nonnegative",
        ),
        CheckConstraint(
            "freelancer_award_minor = freelancer_net_minor + commission_minor",
            name="ck_dispute_decisions_freelancer_breakdown",
        ),
        UniqueConstraint("dispute_id", name="uq_dispute_decisions_dispute_id"),
        UniqueConstraint(
            "journal_transaction_id",
            name="uq_dispute_decisions_journal_transaction_id",
        ),
        UniqueConstraint("refund_id", name="uq_dispute_decisions_refund_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    dispute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False
    )
    administrator_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    freelancer_award_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    freelancer_net_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    client_refund_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    commission_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    journal_transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("journal_transactions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    refund_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("refunds.id", ondelete="RESTRICT"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    dispute: Mapped[Dispute] = relationship(back_populates="decision")


def _set_dispute_event_timestamp(
    target: DisputeEvent, _args: tuple[object, ...], kwargs: dict[str, object]
) -> None:
    if "created_at" not in kwargs:
        target.created_at = datetime.now(UTC)


def _reject_dispute_record_mutation(
    _mapper: object,
    _connection: object,
    _target: DisputeParty | DisputeEvidence | DisputeEvent | DisputeDecision,
) -> None:
    raise ValueError("Dispute evidence, parties, events, and decisions are immutable")


event.listen(DisputeEvent, "init", _set_dispute_event_timestamp)
for model in (DisputeParty, DisputeEvidence, DisputeEvent, DisputeDecision):
    event.listen(model, "before_update", _reject_dispute_record_mutation)
    event.listen(model, "before_delete", _reject_dispute_record_mutation)
