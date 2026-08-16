from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class PortfolioItem(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "portfolio_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    freelancer_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("freelancer_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    external_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    files: Mapped[list[PortfolioFile]] = relationship(
        back_populates="item", cascade="all, delete-orphan", lazy="selectin"
    )


class PortfolioFile(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "portfolio_files"
    __table_args__ = (
        CheckConstraint("file_size_bytes >= 0", name="ck_portfolio_files_file_size_nonnegative"),
        CheckConstraint(
            "scan_status IN ('QUARANTINED', 'SCANNING', 'SAFE', 'REJECTED')",
            name="ck_portfolio_files_scan_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    portfolio_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("portfolio_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    object_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUARANTINED")

    item: Mapped[PortfolioItem] = relationship(back_populates="files")
