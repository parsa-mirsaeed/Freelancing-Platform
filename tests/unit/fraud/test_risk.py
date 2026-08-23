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
    for _index in range(5):
        response = client.post(
            "/api/v1/admin/risk/assessments",
            headers=auth_header(admin),
            json={"subject_user_id": subject["user"]["id"], "text": text},
        )
        assert response.status_code == 201
        responses.append(response.get_json())

    assert responses[0]["review_status"] == "NOT_REQUIRED"
    assert responses[1]["review_status"] == "NOT_REQUIRED"
    assessment = responses[-1]
    assert assessment["risk_score_basis_points"] >= 6000
    assert assessment["review_status"] == "PENDING"
    assert "off_platform_contact" in assessment["reasons"]
    assert "url_spam" in assessment["reasons"]
    assert "duplicate_text" in assessment["reasons"]
    assert assessment["automatic_action"] is None
    assert "text" not in assessment

    queue = client.get(
        "/api/v1/admin/risk/assessments?status=PENDING&limit=2",
        headers=auth_header(admin),
    )
    assert queue.status_code == 200
    queue_body = queue.get_json()
    assert len(queue_body["items"]) == 2
    assert queue_body["next_after"] is not None
    assert all(item["review_status"] == "PENDING" for item in queue_body["items"])
    assert all(item["automatic_action"] is None for item in queue_body["items"])

    next_page = client.get(
        f"/api/v1/admin/risk/assessments?status=PENDING&limit=2&after={queue_body['next_after']}",
        headers=auth_header(admin),
    )
    assert next_page.status_code == 200
    assert len(next_page.get_json()["items"]) == 1

    reviewed = client.post(
        f"/api/v1/admin/risk/assessments/{assessment['id']}/review",
        headers=auth_header(admin),
        json={"decision": "ESCALATE", "note": "Manual investigation required"},
    )
    assert reviewed.status_code == 200
    reviewed_body = reviewed.get_json()
    assert reviewed_body["review_status"] == "ESCALATED"
    assert reviewed_body["automatic_action"] is None


def test_risk_queue_rejects_invalid_filters(client, app) -> None:  # type: ignore[no-untyped-def]
    admin = _admin(client, app)
    invalid_status = client.get(
        "/api/v1/admin/risk/assessments?status=AUTO_BANNED",
        headers=auth_header(admin),
    )
    assert invalid_status.status_code == 422

    invalid_limit = client.get(
        "/api/v1/admin/risk/assessments?limit=101",
        headers=auth_header(admin),
    )
    assert invalid_limit.status_code == 422


def test_non_admin_cannot_request_or_list_risk_scores(client) -> None:  # type: ignore[no-untyped-def]
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
    listed = client.get(
        "/api/v1/admin/risk/assessments",
        headers=auth_header(requester),
    )
    assert listed.status_code == 403
