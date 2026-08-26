from __future__ import annotations

import uuid

import pytest

from app.extensions import db
from app.identity.mfa import totp_code_for_secret
from app.identity.models import UserRole
from app.payouts.models import PayoutProviderAccount
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


class FakeProvider:
    name = "stripe"

    def validate_payout_destination(self, *, reference: str) -> str:
        if not reference.startswith("acct_"):
            raise AssertionError("test expected a Stripe connected account id")
        return reference


def _admin(client, app):  # type: ignore[no-untyped-def]
    admin = register_user(
        client,
        email="payout-admin@example.com",
        role="employer",
    )
    with app.app_context():
        db.session.add(UserRole(user_id=uuid.UUID(admin["user"]["id"]), role="admin"))
        db.session.commit()
    enrolled = client.post(
        "/api/v1/auth/mfa/totp/enroll",
        headers=auth_header(admin),
        json={"password": "correct horse battery staple"},
    )
    assert enrolled.status_code == 200
    confirmed = client.post(
        "/api/v1/auth/mfa/totp/confirm",
        headers=auth_header(admin),
        json={"code": totp_code_for_secret(enrolled.get_json()["secret"])},
    )
    assert confirmed.status_code == 200
    return admin


def test_admin_can_configure_and_disable_verified_payout_destination(
    client,
    app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    admin = _admin(client, app)
    freelancer = register_user(
        client,
        email="payout-freelancer@example.com",
        role="freelancer",
    )
    monkeypatch.setattr(
        "app.payouts.provider_accounts.get_provider",
        lambda _name: FakeProvider(),
    )

    path = (
        "/api/v1/admin/freelancers/"
        f"{freelancer['user']['id']}/payout-provider-accounts/stripe"
    )
    configured = client.put(
        path,
        headers=auth_header(admin),
        json={"external_account_reference": "acct_verified"},
    )
    assert configured.status_code == 200
    body = configured.get_json()
    assert body["provider"] == "stripe"
    assert body["external_account_reference"] == "acct_verified"
    assert body["status"] == "ACTIVE"

    with app.app_context():
        account = db.session.scalar(
            db.select(PayoutProviderAccount).where(
                PayoutProviderAccount.freelancer_user_id
                == uuid.UUID(freelancer["user"]["id"]),
                PayoutProviderAccount.provider == "stripe",
            )
        )
        assert account is not None
        assert account.external_account_reference == "acct_verified"
        assert account.status == "ACTIVE"

    disabled = client.delete(path, headers=auth_header(admin))
    assert disabled.status_code == 200
    assert disabled.get_json()["status"] == "DISABLED"


def test_non_admin_cannot_configure_payout_destination(
    client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    employer = register_user(
        client,
        email="payout-employer@example.com",
        role="employer",
    )
    freelancer = register_user(
        client,
        email="payout-target@example.com",
        role="freelancer",
    )
    monkeypatch.setattr(
        "app.payouts.provider_accounts.get_provider",
        lambda _name: FakeProvider(),
    )
    response = client.put(
        (
            "/api/v1/admin/freelancers/"
            f"{freelancer['user']['id']}/payout-provider-accounts/stripe"
        ),
        headers=auth_header(employer),
        json={"external_account_reference": "acct_verified"},
    )
    assert response.status_code == 403
