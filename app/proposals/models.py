from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Proposal(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'SUBMITTED', 'UNDER_NEGOTIATION', "
            "'WITHDRAWN', 'REJECTED', 'ACCEPTED')",
            name="ck_proposals_status",
        ),
        CheckConstraint("current_version >= 1", name="ck_proposals_current_version_positive"),
        UniqueConstraint("project_id", "freelancer_user_id", name="uq_proposal_project_freelancer"),
        Index(
            "uq_proposals_one_accepted_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("status = 'ACCEPTED'"),
            sqlite_where=text("status = 'ACCEPTED'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    freelancer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    versions: Mapped[list[ProposalVersion]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
        order_by="ProposalVersion.version_number",
        lazy="selectin",
    )


class ProposalVersion(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "proposal_versions"
    __table_args__ = (
        CheckConstraint("version_number >= 1", name="ck_proposal_versions_version_positive"),
        CheckConstraint("amount_minor >= 0", name="ck_proposal_versions_amount_nonnegative"),
        CheckConstraint("delivery_days >= 1", name="ck_proposal_versions_delivery_positive"),
        UniqueConstraint("proposal_id", "version_number", name="uq_proposal_version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    delivery_days: Mapped[int] = mapped_column(Integer, nullable=False)
    cover_letter: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    proposal: Mapped[Proposal] = relationship(back_populates="versions")
    milestones: Mapped[list[ProposalMilestone]] = relationship(
        back_populates="proposal_version",
        cascade="all, delete-orphan",
        order_by="ProposalMilestone.sequence",
        lazy="selectin",
    )


class ProposalMilestone(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "proposal_milestones"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="ck_proposal_milestones_sequence_positive"),
        CheckConstraint("amount_minor >= 0", name="ck_proposal_milestones_amount_nonnegative"),
        CheckConstraint("delivery_days >= 1", name="ck_proposal_milestones_delivery_positive"),
        UniqueConstraint("proposal_version_id", "sequence", name="uq_proposal_milestone_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    proposal_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("proposal_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delivery_days: Mapped[int] = mapped_column(Integer, nullable=False)

    proposal_version: Mapped[ProposalVersion] = relationship(back_populates="milestones")
