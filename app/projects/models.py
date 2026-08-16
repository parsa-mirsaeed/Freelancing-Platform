from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.freelancers.models import Skill


class Project(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSED', 'CANCELLED')", name="ck_projects_status"),
        CheckConstraint(
            "(budget_min_minor IS NULL AND budget_max_minor IS NULL AND currency IS NULL) OR "
            "(budget_min_minor IS NOT NULL AND budget_max_minor IS NOT NULL "
            "AND currency IS NOT NULL AND budget_min_minor >= 0 "
            "AND budget_max_minor >= budget_min_minor)",
            name="ck_projects_budget_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    employer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    budget_min_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    budget_max_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    skill_links: Mapped[list[ProjectSkill]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    attachments: Mapped[list[ProjectAttachment]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    invites: Mapped[list[ProjectInvite]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectSkill(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "project_skills"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skills.id", ondelete="RESTRICT"), primary_key=True
    )

    project: Mapped[Project] = relationship(back_populates="skill_links")
    skill: Mapped[Skill] = relationship(lazy="joined")


class ProjectAttachment(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "project_attachments"
    __table_args__ = (
        CheckConstraint(
            "file_size_bytes >= 0", name="ck_project_attachments_file_size_nonnegative"
        ),
        CheckConstraint(
            "scan_status IN ('QUARANTINED', 'SCANNING', 'SAFE', 'REJECTED')",
            name="ck_project_attachments_scan_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUARANTINED")

    project: Mapped[Project] = relationship(back_populates="attachments")


class ProjectInvite(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "project_invites"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'DECLINED', 'CANCELLED')",
            name="ck_project_invites_status",
        ),
        UniqueConstraint("project_id", "freelancer_user_id", name="uq_project_invite_freelancer"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    freelancer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="invites")
