from __future__ import annotations

import base64

import pytest
from sqlalchemy import text

from app.config import Settings
from app.extensions import db
from app.identity.pii import PiiCipher

pytestmark = pytest.mark.unit


def _key(fill: int) -> str:
    return base64.urlsafe_b64encode(bytes([fill]) * 32).decode("ascii").rstrip("=")


def test_pii_cipher_is_randomized_context_bound_and_lookup_is_stable() -> None:
    cipher = PiiCipher.from_config(f"key-a:{_key(1)}", _key(9))
    email = "person@example.com"

    first = cipher.encrypt(email, context="user.email")
    second = cipher.encrypt(email, context="user.email")

    assert first != second
    assert email not in first
    assert first.startswith("v1:key-a:")
    assert cipher.decrypt(first, context="user.email") == email
    assert cipher.blind_index(email, context="user.email") == cipher.blind_index(
        email, context="user.email"
    )
    assert cipher.blind_index(email, context="user.email") != cipher.blind_index(
        email, context="different-field"
    )
    with pytest.raises(ValueError, match="Invalid PII ciphertext"):
        cipher.decrypt(first, context="different-field")


def test_pii_keyring_decrypts_old_key_and_rewraps_to_active_key() -> None:
    old = PiiCipher.from_config(f"old:{_key(1)}", _key(9))
    encrypted = old.encrypt("person@example.com", context="user.email")

    rotated = PiiCipher.from_config(f"new:{_key(2)},old:{_key(1)}", _key(9))
    assert rotated.needs_rotation(encrypted) is True
    assert rotated.decrypt(encrypted, context="user.email") == "person@example.com"

    rewrapped = rotated.rewrap(encrypted, context="user.email")
    assert rewrapped.startswith("v1:new:")
    assert rotated.needs_rotation(rewrapped) is False
    assert rotated.decrypt(rewrapped, context="user.email") == "person@example.com"


def test_registration_persists_no_plaintext_email_and_lookup_remains_case_insensitive(
    client,
) -> None:  # type: ignore[no-untyped-def]
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": " Protected.Person@Example.com ",
            "password": "correct horse battery staple",
            "role": "freelancer",
        },
    )
    assert registered.status_code == 201
    assert registered.get_json()["user"]["email"] == "protected.person@example.com"

    row = (
        db.session.execute(text("SELECT email_ciphertext, email_lookup_hash FROM users"))
        .mappings()
        .one()
    )
    assert "protected.person@example.com" not in row["email_ciphertext"]
    assert row["email_ciphertext"].startswith("v1:")
    assert len(row["email_lookup_hash"]) == 64

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "PROTECTED.PERSON@EXAMPLE.COM",
            "password": "correct horse battery staple",
        },
    )
    assert login.status_code == 200
    assert login.get_json()["user"]["email"] == "protected.person@example.com"

    duplicate = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Protected.Person@Example.com",
            "password": "correct horse battery staple",
            "role": "employer",
        },
    )
    assert duplicate.status_code == 409
    assert duplicate.get_json()["type"] == "email_in_use"


def test_production_requires_explicit_pii_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "production-secret-key-with-enough-entropy")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://marketplace.example")
    monkeypatch.delenv("PII_ENCRYPTION_KEYS", raising=False)
    monkeypatch.delenv("PII_LOOKUP_KEY", raising=False)

    with pytest.raises(RuntimeError, match="PII_ENCRYPTION_KEYS"):
        Settings.from_env()


def test_invalid_pii_key_material_fails_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("PII_ENCRYPTION_KEYS", "active:not-base64!")
    monkeypatch.setenv("PII_LOOKUP_KEY", _key(8))

    with pytest.raises(RuntimeError, match="URL-safe base64"):
        Settings.from_env()
