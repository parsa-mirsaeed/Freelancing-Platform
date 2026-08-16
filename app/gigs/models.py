from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Gig(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "gigs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    freelancer_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("freelancer_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    packages: Mapped[list[GigPackage]] = relationship(
        back_populates="gig", cascade="all, delete-orphan", lazy="selectin"
    )
    requirements: Mapped[list[GigRequirement]] = relationship(
        back_populates="gig", cascade="all, delete-orphan", lazy="selectin"
    )


class GigPackage(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "gig_packages"
    __table_args__ = (
        CheckConstraint("tier IN ('BASIC', 'STANDARD', 'PREMIUM')", name="ck_gig_packages_tier"),
        CheckConstraint("amount_minor >= 0", name="ck_gig_packages_amount_nonnegative"),
        CheckConstraint("delivery_days >= 1", name="ck_gig_packages_delivery_positive"),
        CheckConstraint("revisions >= 0", name="ck_gig_packages_revisions_nonnegative"),
        UniqueConstraint("gig_id", "tier", name="uq_gig_package_tier"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gig_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("gigs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    delivery_days: Mapped[int] = mapped_column(Integer, nullable=False)
    revisions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    gig: Mapped[Gig] = relationship(back_populates="packages")


class GigRequirement(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "gig_requirements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    gig_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("gigs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt: Mapped[str] = mapped_column(String(500), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    gig: Mapped[Gig] = relationship(back_populates="requirements")
