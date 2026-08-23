from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.extensions import db
from app.identity.mfa import totp_code_for_secret
from app.identity.models import User, UserDevice, UserRole
from app.identity.pii import current_pii_cipher

pytestmark = pytest.mark.unit

PASSWORD = "correct horse battery staple"
_EMAIL_CONTEXT = "user.email"


def _email_lookup_hash(email: str) -> str:
    return current_pii_cipher().blind_index(email.strip().lower(), context=_EMAIL_CONTEXT)


def _register(client, *, email: str = "secure@example.com", role: str = "freelancer") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "role": role},
        headers={"X-Device-ID": "browser-a", "User-Agent": "security-test"},
    )
    assert response.status_code == 201
    return response.get_json()


def _login(client, *, email: str = "secure@example.com", device: str = "browser-a") -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={"X-Device-ID": device, "User-Agent": "security-test"},
    )
    assert response.status_code == 200
    return response.get_json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _enable_mfa(client, token: str) -> tuple[str, list[str]]:
    enroll = client.post(
        "/api/v1/auth/mfa/totp/enroll",
        headers=_auth(token),
        json={"password": PASSWORD},
    )
    assert enroll.status_code == 200
    secret = enroll.get_json()["secret"]
    confirm = client.post(
        "/api/v1/auth/mfa/totp/confirm",
        headers=_auth(token),
        json={"code": totp_code_for_secret(secret)},
    )
    assert confirm.status_code == 200
    recovery_codes = confirm.get_json()["recovery_codes"]
    assert len(recovery_codes) == 8
    return secret, recovery_codes


def test_totp_enrollment_and_session_step_up(client) -> None:  # type: ignore[no-untyped-def]
    registered = _register(client)
    secret, _ = _enable_mfa(client, registered["access_token"])

    fresh = _login(client)
    status = client.get("/api/v1/auth/mfa", headers=_auth(fresh["access_token"]))
    assert status.status_code == 200
    assert status.get_json()["enabled"] is True
    assert status.get_json()["verified_until"] is None

    assert_response = client.post("/api/v1/auth/mfa/assert", headers=_auth(fresh["access_token"]))
    assert assert_response.status_code == 403
    assert assert_response.get_json()["type"] == "mfa_required"

    verified = client.post(
        "/api/v1/auth/mfa/verify",
        headers=_auth(fresh["access_token"]),
        json={"code": totp_code_for_secret(secret)},
    )
    assert verified.status_code == 200
    assert verified.get_json()["verified_until"] is not None
    assert (
        client.post("/api/v1/auth/mfa/assert", headers=_auth(fresh["access_token"])).status_code
        == 204
    )


def test_recovery_code_is_one_time(client) -> None:  # type: ignore[no-untyped-def]
    registered = _register(client)
    _, recovery_codes = _enable_mfa(client, registered["access_token"])
    recovery_code = recovery_codes[0]

    first = _login(client, device="browser-b")
    response = client.post(
        "/api/v1/auth/mfa/verify",
        headers=_auth(first["access_token"]),
        json={"code": recovery_code},
    )
    assert response.status_code == 200
    assert response.get_json()["recovery_code_used"] is True

    second = _login(client, device="browser-c")
    replay = client.post(
        "/api/v1/auth/mfa/verify",
        headers=_auth(second["access_token"]),
        json={"code": recovery_code},
    )
    assert replay.status_code == 401
    assert replay.get_json()["type"] == "invalid_mfa_code"


def test_failed_login_lock_is_generic_and_recovers_after_window(
    client,  # type: ignore[no-untyped-def]
) -> None:
    _register(client)
    for _ in range(5):
        failed = client.post(
            "/api/v1/auth/login",
            json={"email": "secure@example.com", "password": "wrong password value"},
        )
        assert failed.status_code == 401
        assert failed.get_json()["type"] == "invalid_credentials"

    locked = client.post(
        "/api/v1/auth/login",
        json={"email": "secure@example.com", "password": PASSWORD},
    )
    assert locked.status_code == 401
    assert locked.get_json()["type"] == "invalid_credentials"

    user = db.session.scalar(
        select(User).where(User.email_lookup_hash == _email_lookup_hash("secure@example.com"))
    )
    assert user is not None and user.locked_until is not None
    user.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    db.session.commit()
    assert _login(client)["user"]["email"] == "secure@example.com"


def test_device_registry_deduplicates_and_detects_new_devices(
    client,  # type: ignore[no-untyped-def]
) -> None:
    _register(client)
    _login(client, device="browser-a")
    _login(client, device="browser-b")
    devices = db.session.scalars(select(UserDevice)).all()
    assert len(devices) == 2
    assert all(len(device.fingerprint_hash) == 64 for device in devices)
    assert all(len(device.user_agent_hash) == 64 for device in devices)


def test_admin_routes_require_fresh_mfa(client) -> None:  # type: ignore[no-untyped-def]
    registered = _register(client, email="admin@example.com", role="employer")
    user = db.session.scalar(
        select(User).where(User.email_lookup_hash == _email_lookup_hash("admin@example.com"))
    )
    assert user is not None
    user.roles.append(UserRole(role="admin"))
    db.session.commit()
    secret, _ = _enable_mfa(client, registered["access_token"])

    fresh = _login(client, email="admin@example.com", device="admin-fresh")
    blocked = client.get("/api/v1/admin/risk/assessments", headers=_auth(fresh["access_token"]))
    assert blocked.status_code == 403
    assert blocked.get_json()["type"] == "mfa_required"

    challenge = client.post(
        "/api/v1/auth/mfa/verify",
        headers=_auth(fresh["access_token"]),
        json={"code": totp_code_for_secret(secret)},
    )
    assert challenge.status_code == 200
    allowed = client.get("/api/v1/admin/risk/assessments", headers=_auth(fresh["access_token"]))
    assert allowed.status_code == 200


def test_payout_requires_mfa_before_business_service(
    client,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    registered = _register(client)
    secret, _ = _enable_mfa(client, registered["access_token"])
    fresh = _login(client, device="payout-fresh")

    def fake_create_payout(**kwargs):  # type: ignore[no-untyped-def]
        return {"payout_id": "test", "status": "REQUESTED"}, 201

    monkeypatch.setattr("app.payouts.api.create_payout", fake_create_payout)
    payload = {"amount_minor": 100, "currency": "USD", "provider": "sandbox"}
    blocked = client.post(
        "/api/v1/payouts",
        headers={**_auth(fresh["access_token"]), "Idempotency-Key": "payout-test"},
        json=payload,
    )
    assert blocked.status_code == 403
    assert blocked.get_json()["type"] == "mfa_required"

    assert (
        client.post(
            "/api/v1/auth/mfa/verify",
            headers=_auth(fresh["access_token"]),
            json={"code": totp_code_for_secret(secret)},
        ).status_code
        == 200
    )
    allowed = client.post(
        "/api/v1/payouts",
        headers={**_auth(fresh["access_token"]), "Idempotency-Key": "payout-test"},
        json=payload,
    )
    assert allowed.status_code == 201


def test_mfa_enrollment_requires_current_password(client) -> None:  # type: ignore[no-untyped-def]
    registered = _register(client)
    rejected = client.post(
        "/api/v1/auth/mfa/totp/enroll",
        headers=_auth(registered["access_token"]),
        json={"password": "not-the-current-password"},
    )
    assert rejected.status_code == 401
    assert rejected.get_json()["type"] == "invalid_credentials"
