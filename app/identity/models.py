from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.identity.pii import current_pii_cipher

_EMAIL_CONTEXT = "user.email"


class User(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email_lookup_hash", name="uq_users_email_lookup_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    _email_ciphertext: Mapped[str] = mapped_column("email_ciphertext", String(1024), nullable=False)
    email_lookup_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_seed: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    roles: Mapped[list[UserRole]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    devices: Mapped[list[UserDevice]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    verifications: Mapped[list[UserVerification]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def email(self) -> str:
        return current_pii_cipher().decrypt(self._email_ciphertext, context=_EMAIL_CONTEXT)

    @email.setter
    def email(self, value: str) -> None:
        normalized = value.strip().lower()
        cipher = current_pii_cipher()
        self._email_ciphertext = cipher.encrypt(normalized, context=_EMAIL_CONTEXT)
        self.email_lookup_hash = cipher.blind_index(normalized, context=_EMAIL_CONTEXT)

    def rotate_email_encryption_if_needed(self) -> bool:
        cipher = current_pii_cipher()
        if not cipher.needs_rotation(self._email_ciphertext):
            return False
        self._email_ciphertext = cipher.rewrap(self._email_ciphertext, context=_EMAIL_CONTEXT)
        return True


class UserRole(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(40), primary_key=True)

    user: Mapped[User] = relationship(back_populates="roles")


class UserDevice(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "user_devices"
    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint_hash", name="uq_user_devices_user_fingerprint"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_agent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="devices")


class UserSession(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user_devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    refresh_jti_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="sessions")
    device: Mapped[UserDevice | None] = relationship()


class UserVerification(db.Model):  # type: ignore[name-defined,misc]
    __tablename__ = "user_verifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="verifications")
