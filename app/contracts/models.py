from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

if TYPE_CHECKING:
    from app.milestones.models import Milestone


class Contract(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "contracts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING_SIGNATURES', 'ACTIVE', 'CANCELLED')",
            name="ck_contracts_status",
        ),
        CheckConstraint("current_version >= 1", name="ck_contracts_current_version_positive"),
        UniqueConstraint("project_id", name="uq_contracts_project_id"),
        UniqueConstraint("accepted_proposal_id", name="uq_contracts_accepted_proposal_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    accepted_proposal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("proposals.id", ondelete="RESTRICT"), nullable=False
    )
    employer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    freelancer_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING_SIGNATURES")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list[ContractVersion]] = relationship(
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="ContractVersion.version_number",
        lazy="selectin",
    )
    parties: Mapped[list[ContractParty]] = relationship(
        back_populates="contract", cascade="all, delete-orphan", lazy="selectin"
    )


class ContractVersion(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "contract_versions"
    __table_args__ = (
        CheckConstraint("version_number >= 1", name="ck_contract_versions_version_positive"),
        UniqueConstraint("contract_id", "version_number", name="uq_contract_version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    contract: Mapped[Contract] = relationship(back_populates="versions")
    signatures: Mapped[list[ContractSignature]] = relationship(
        back_populates="contract_version", cascade="all, delete-orphan", lazy="selectin"
    )
    milestones: Mapped[list[Milestone]] = relationship(
        back_populates="contract_version",
        cascade="all, delete-orphan",
        order_by="Milestone.sequence",
        lazy="selectin",
    )


class ContractParty(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "contract_parties"
    __table_args__ = (
        CheckConstraint("role IN ('EMPLOYER', 'FREELANCER')", name="ck_contract_parties_role"),
    )

    contract_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("contracts.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    required_signature: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    contract: Mapped[Contract] = relationship(back_populates="parties")


class ContractSignature(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "contract_signatures"
    __table_args__ = (
        UniqueConstraint(
            "contract_version_id", "user_id", name="uq_contract_signature_version_user"
        ),
        UniqueConstraint(
            "user_id", "idempotency_key_hash", name="uq_contract_signature_idempotency"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    contract_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("contract_versions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    risk_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    signature_provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    contract_version: Mapped[ContractVersion] = relationship(back_populates="signatures")


def _reject_contract_version_mutation(
    _mapper: object, _connection: object, _target: ContractVersion
) -> None:
    raise ValueError("Contract versions are immutable; create a new version instead")


def _reject_signature_mutation(
    _mapper: object, _connection: object, _target: ContractSignature
) -> None:
    raise ValueError("Contract signatures are immutable")


event.listen(ContractVersion, "before_update", _reject_contract_version_mutation)
event.listen(ContractVersion, "before_delete", _reject_contract_version_mutation)
event.listen(ContractSignature, "before_update", _reject_signature_mutation)
event.listen(ContractSignature, "before_delete", _reject_signature_mutation)
