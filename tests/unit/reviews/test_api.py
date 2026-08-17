import uuid

import pytest
from sqlalchemy import select

from app.common.models import OutboxEvent
from app.extensions import db
from app.milestones.models import Milestone
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def test_review_requires_completed_contract_backed_project(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer = register_user(client, email="review-employer@example.com", role="employer")
    freelancer = register_user(client, email="review-freelancer@example.com", role="freelancer")
    freelancer_headers = auth_header(freelancer)
    assert (
        client.put(
            "/api/v1/freelancers/me/profile",
            headers=freelancer_headers,
            json={"title": "Engineer", "skills": ["Python"]},
        ).status_code
        == 200
    )
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Project", "description": "Work", "skills": ["Python"]},
    ).get_json()
    proposal = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=freelancer_headers,
        json={"amount_minor": 1000, "currency": "USD", "delivery_days": 3},
    ).get_json()
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/submit", headers=freelancer_headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/accept", headers=auth_header(employer)
        ).status_code
        == 200
    )

    early = client.post(
        f"/api/v1/projects/{project['id']}/reviews",
        headers=auth_header(employer),
        json={"rating": 5, "comment": "Great"},
    )
    assert early.status_code == 409

    contract = client.get(
        f"/api/v1/projects/{project['id']}/contract", headers=auth_header(employer)
    ).get_json()
    document_hash = contract["version"]["document_hash"]
    for key, user in (("review-employer-sign", employer), ("review-freelancer-sign", freelancer)):
        signed = client.post(
            f"/api/v1/contracts/{contract['id']}/sign",
            headers={**auth_header(user), "Idempotency-Key": key},
            json={"document_hash": document_hash},
        )
        assert signed.status_code == 200

    milestone_id = uuid.UUID(contract["version"]["milestones"][0]["id"])
    milestone = db.session.get(Milestone, milestone_id)
    assert milestone is not None
    milestone.status = "RELEASED"
    db.session.commit()

    assert (
        client.post(
            f"/api/v1/projects/{project['id']}/close", headers=auth_header(employer)
        ).status_code
        == 200
    )
    review = client.post(
        f"/api/v1/projects/{project['id']}/reviews",
        headers=auth_header(employer),
        json={"rating": 5, "comment": "Great"},
    )
    assert review.status_code == 201
    assert review.get_json()["rating"] == 5
    assert len(list(db.session.scalars(select(OutboxEvent)))) >= 2
