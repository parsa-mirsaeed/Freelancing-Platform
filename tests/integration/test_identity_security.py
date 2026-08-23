from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app import create_app
from app.extensions import db
from app.identity.mfa import totp_code_for_secret
from app.identity.models import User, UserDevice, UserVerification

pytestmark = pytest.mark.db

PASSWORD = "correct horse battery staple"


def _app():  # type: ignore[no-untyped-def]
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "identity-security-integration-secret",
            "MFA_SECRET_KEY": "identity-security-mfa-secret",
            "SQLALCHEMY_DATABASE_URI": os.environ["DATABASE_URL"],
            "REDIS_URL": "redis://localhost:6379/15",
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_INDEX_PREFIX": "identity-security-unused",
            "AUTH_MAX_FAILED_ATTEMPTS": 5,
            "AUTH_LOCK_SECONDS": 900,
            "MFA_STEP_UP_TTL_SECONDS": 600,
        }
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_mfa_step_up_recovery_and_device_state_persist_on_postgres() -> None:
    app = _app()
    email = f"identity-security-{uuid.uuid4()}@example.com"
    with app.test_client() as client:
        registered = client.post(
            "/api/v1/auth/register",
            headers={"X-Device-ID": "integration-browser", "User-Agent": "identity-integration"},
            json={"email": email, "password": PASSWORD, "role": "freelancer"},
        )
        assert registered.status_code == 201
        registered_body = registered.get_json()
        enroll = client.post(
            "/api/v1/auth/mfa/totp/enroll",
            headers=_auth(registered_body["access_token"]),
            json={"password": PASSWORD},
        )
        assert enroll.status_code == 200
        secret = enroll.get_json()["secret"]
        confirm = client.post(
            "/api/v1/auth/mfa/totp/confirm",
            headers=_auth(registered_body["access_token"]),
            json={"code": totp_code_for_secret(secret)},
        )
        assert confirm.status_code == 200
        recovery_code = confirm.get_json()["recovery_codes"][0]

        fresh = client.post(
            "/api/v1/auth/login",
            headers={"X-Device-ID": "integration-browser", "User-Agent": "identity-integration"},
            json={"email": email, "password": PASSWORD},
        )
        assert fresh.status_code == 200
        fresh_body = fresh.get_json()
        assert (
            client.post(
                "/api/v1/auth/mfa/assert",
                headers=_auth(fresh_body["access_token"]),
            ).status_code
            == 403
        )
        verified = client.post(
            "/api/v1/auth/mfa/verify",
            headers=_auth(fresh_body["access_token"]),
            json={"code": recovery_code},
        )
        assert verified.status_code == 200
        assert verified.get_json()["recovery_code_used"] is True
        assert (
            client.post(
                "/api/v1/auth/mfa/assert",
                headers=_auth(fresh_body["access_token"]),
            ).status_code
            == 204
        )

    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == email))
        assert user is not None and user.mfa_enabled_at is not None
        device_count = db.session.scalar(
            select(func.count(UserDevice.id)).where(UserDevice.user_id == user.id)
        )
        assert device_count == 1
        assert (
            db.session.scalar(
                select(func.count(UserVerification.id)).where(
                    UserVerification.user_id == user.id,
                    UserVerification.kind == "mfa_recovery",
                    UserVerification.consumed_at.is_not(None),
                )
            )
            == 1
        )


def test_account_lock_persists_and_expires_on_postgres() -> None:
    app = _app()
    email = f"identity-lock-{uuid.uuid4()}@example.com"
    with app.test_client() as client:
        assert (
            client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": PASSWORD, "role": "employer"},
            ).status_code
            == 201
        )
        for _ in range(5):
            failed = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "definitely-not-the-password"},
            )
            assert failed.status_code == 401
            assert failed.get_json()["type"] == "invalid_credentials"
        locked = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": PASSWORD},
        )
        assert locked.status_code == 401
        assert locked.get_json()["type"] == "invalid_credentials"

    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == email).with_for_update())
        assert user is not None and user.locked_until is not None
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        assert locked_until > datetime.now(UTC) - timedelta(seconds=1)
        user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()

    with app.test_client() as client:
        recovered = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": PASSWORD},
        )
        assert recovered.status_code == 200
