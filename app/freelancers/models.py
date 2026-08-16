from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class FreelancerProfile(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "freelancer_profiles"
    __table_args__ = (
        CheckConstraint(
            "(hourly_rate_minor IS NULL AND currency IS NULL) OR "
            "(hourly_rate_minor IS NOT NULL AND hourly_rate_minor >= 0 "
            "AND currency IS NOT NULL)",
            name="ck_freelancer_profiles_hourly_rate_currency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    bio: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hourly_rate_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    accepting_work: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    languages: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    projection_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    skill_links: Mapped[list[FreelancerSkill]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )
    availability_rules: Mapped[list[AvailabilityRule]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )
    availability_exceptions: Mapped[list[AvailabilityException]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )


class Skill(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    freelancer_links: Mapped[list[FreelancerSkill]] = relationship(back_populates="skill")


class FreelancerSkill(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "freelancer_skills"

    freelancer_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("freelancer_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )

    profile: Mapped[FreelancerProfile] = relationship(back_populates="skill_links")
    skill: Mapped[Skill] = relationship(back_populates="freelancer_links", lazy="joined")


class AvailabilityRule(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "availability_rules"
    __table_args__ = (
        CheckConstraint(
            "weekday >= 0 AND weekday <= 6", name="ck_availability_rules_weekday_range"
        ),
        CheckConstraint("start_time < end_time", name="ck_availability_rules_time_range"),
        UniqueConstraint(
            "freelancer_profile_id",
            "weekday",
            "start_time",
            "end_time",
            name="uq_availability_rule_slot",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    freelancer_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("freelancer_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)

    profile: Mapped[FreelancerProfile] = relationship(back_populates="availability_rules")


class AvailabilityException(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "availability_exceptions"
    __table_args__ = (
        CheckConstraint(
            "(start_time IS NULL AND end_time IS NULL) OR "
            "(start_time IS NOT NULL AND end_time IS NOT NULL AND start_time < end_time)",
            name="ck_availability_exceptions_optional_time_range",
        ),
        UniqueConstraint(
            "freelancer_profile_id", "exception_date", name="uq_availability_exception_date"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    freelancer_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("freelancer_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    exception_date: Mapped[date] = mapped_column(Date, nullable=False)
    available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(240), nullable=True)

    profile: Mapped[FreelancerProfile] = relationship(back_populates="availability_exceptions")
