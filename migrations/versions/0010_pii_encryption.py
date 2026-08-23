"""encrypt identity email at rest with a keyed blind index

Revision ID: 0010_pii_encryption
Revises: 0009_identity_security
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.config import Settings
from app.identity.pii import PiiCipher

revision: str = "0010_pii_encryption"
down_revision: str | None = "0009_identity_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMAIL_CONTEXT = "user.email"


def upgrade() -> None:
    op.add_column("users", sa.Column("email_ciphertext", sa.String(length=1024), nullable=True))
    op.add_column("users", sa.Column("email_lookup_hash", sa.String(length=64), nullable=True))

    cipher = _cipher()
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, email FROM users ORDER BY id")).mappings()
    for row in rows:
        normalized_email = str(row["email"]).strip().lower()
        connection.execute(
            sa.text(
                "UPDATE users SET email_ciphertext = :ciphertext, email_lookup_hash = :lookup "
                "WHERE id = :user_id"
            ),
            {
                "ciphertext": cipher.encrypt(normalized_email, context=_EMAIL_CONTEXT),
                "lookup": cipher.blind_index(normalized_email, context=_EMAIL_CONTEXT),
                "user_id": row["id"],
            },
        )

    op.alter_column("users", "email_ciphertext", existing_type=sa.String(length=1024), nullable=False)
    op.alter_column("users", "email_lookup_hash", existing_type=sa.String(length=64), nullable=False)
    op.create_unique_constraint("uq_users_email_lookup_hash", "users", ["email_lookup_hash"])
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "email")


def downgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))

    cipher = _cipher()
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, email_ciphertext FROM users ORDER BY id")
    ).mappings()
    for row in rows:
        connection.execute(
            sa.text("UPDATE users SET email = :email WHERE id = :user_id"),
            {
                "email": cipher.decrypt(str(row["email_ciphertext"]), context=_EMAIL_CONTEXT),
                "user_id": row["id"],
            },
        )

    op.alter_column("users", "email", existing_type=sa.String(length=320), nullable=False)
    op.create_unique_constraint("uq_users_email", "users", ["email"])
    op.drop_constraint("uq_users_email_lookup_hash", "users", type_="unique")
    op.drop_column("users", "email_lookup_hash")
    op.drop_column("users", "email_ciphertext")


def _cipher() -> PiiCipher:
    settings = Settings.from_env()
    return PiiCipher.from_config(settings.pii_encryption_keys, settings.pii_lookup_key)
