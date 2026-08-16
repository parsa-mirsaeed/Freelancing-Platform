from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.contracts.models import ContractVersion


MILESTONE_STATES = (
    "CREATED",
    "FUNDED",
    "IN_PROGRESS",
    "SUBMITTED",
    "CHANGES_REQUESTED",
    "DISPUTED",
    "APPROVED",
    "RELEASE_PENDING",
    "RELEASED",
)


class Milestone(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "milestones"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="ck_milestones_sequence_positive"),
        CheckConstraint("amount_minor >= 0", name="ck_milestones_amount_nonnegative"),
        CheckConstraint("delivery_days >= 1", name="ck_milestones_delivery_positive"),
        CheckConstraint(
            "status IN ('CREATED', 'FUNDED', 'IN_PROGRESS', 'SUBMITTED', "
            "'CHANGES_REQUESTED', 'DISPUTED', 'APPROVED', 'RELEASE_PENDING', 'RELEASED')",
            name="ck_milestones_status",
        ),
        UniqueConstraint("contract_version_id", "sequence", name="uq_milestone_contract_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    contract_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("contract_versions.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    delivery_days: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="CREATED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    contract_version: Mapped[ContractVersion] = relationship(back_populates="milestones")
    events: Mapped[list[MilestoneEvent]] = relationship(
        back_populates="milestone",
        cascade="all, delete-orphan",
        order_by="MilestoneEvent.created_at",
        lazy="selectin",
    )


class MilestoneEvent(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "milestone_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    milestone_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("milestones.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    from_status: Mapped[str] = mapped_column(String(24), nullable=False)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    milestone: Mapped[Milestone] = relationship(back_populates="events")


def _reject_event_mutation(_mapper: object, _connection: object, _target: MilestoneEvent) -> None:
    raise ValueError("Milestone progress events are append-only")


event.listen(MilestoneEvent, "before_update", _reject_event_mutation)
event.listen(MilestoneEvent, "before_delete", _reject_event_mutation)
