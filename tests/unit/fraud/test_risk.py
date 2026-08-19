from __future__ import annotations

import uuid

import pytest

from app.extensions import db
from app.identity.models import UserRole
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def _admin(client, app):  # type: ignore[no-untyped-def]
    admin = register_user(
        client,
        email="risk-admin@example.com",
        role="employer",
    )
    with app.app_context():
        db.session.add(UserRole(user_id=uuid.UUID(admin["user"]["id"]), role="admin"))
        db.session.commit()
    return admin


def test_risk_score_is_explainable_and_requires_human_decision(client, app) -> None:  # type: ignore[no-untyped-def]
    admin = _admin(client, app)
    subject = register_user(
        client,
        email="risk-subject@example.com",
        role="freelancer",
    )
    text = (
        "Contact me at Telegram and pay outside the platform. "
        "https://spam.example/a https://spam.example/b https://spam.example/c"
    )
    responses = []
    for _index in range(3):
        response = client.post(
            "/api/v1/admin/risk/assessments",
            headers=auth_header(admin),
            json={"subject_user_id": subject["user"]["id"], "text": text},
        )
        assert response.status_code == 201
        responses.append(response.get_json())

    assessment = responses[-1]
    assert assessment["risk_score_basis_points"] >= 6000
    assert assessment["review_status"] == "PENDING"
    assert "off_platform_contact" in assessment["reasons"]
    assert "url_spam" in assessment["reasons"]
    assert "duplicate_text" in assessment["reasons"]
    assert assessment["automatic_action"] is None
    assert "text" not in assessment

    reviewed = client.post(
        f"/api/v1/admin/risk/assessments/{assessment['id']}/review",
        headers=auth_header(admin),
        json={"decision": "ESCALATE", "note": "Manual investigation required"},
    )
    assert reviewed.status_code == 200
    reviewed_body = reviewed.get_json()
    assert reviewed_body["review_status"] == "ESCALATED"
    assert reviewed_body["automatic_action"] is None


def test_non_admin_cannot_request_risk_score(client) -> None:  # type: ignore[no-untyped-def]
    requester = register_user(
        client,
        email="risk-requester@example.com",
        role="employer",
    )
    subject = register_user(
        client,
        email="risk-non-admin-subject@example.com",
        role="freelancer",
    )
    response = client.post(
        "/api/v1/admin/risk/assessments",
        headers=auth_header(requester),
        json={"subject_user_id": subject["user"]["id"], "text": "hello"},
    )
    assert response.status_code == 403
