from __future__ import annotations

import uuid

import pytest

from app.extensions import db
from app.milestones.models import Milestone
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def _active_contract_with_milestone(client):  # type: ignore[no-untyped-def]
    employer = register_user(client, email="milestone-employer@example.com", role="employer")
    freelancer = register_user(client, email="milestone-freelancer@example.com", role="freelancer")
    intruder = register_user(client, email="milestone-intruder@example.com", role="freelancer")
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Milestone project", "description": "Progress", "skills": []},
    ).get_json()
    proposal = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json={
            "amount_minor": 9000,
            "currency": "USD",
            "delivery_days": 9,
            "milestones": [{"title": "Delivery", "amount_minor": 9000, "delivery_days": 9}],
        },
    ).get_json()
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/submit", headers=auth_header(freelancer)
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/proposals/{proposal['id']}/accept", headers=auth_header(employer)
        ).status_code
        == 200
    )
    contract = client.get(
        f"/api/v1/projects/{project['id']}/contract", headers=auth_header(employer)
    ).get_json()
    document_hash = contract["version"]["document_hash"]
    for key, user in (
        ("milestone-sign-employer", employer),
        ("milestone-sign-freelancer", freelancer),
    ):
        response = client.post(
            f"/api/v1/contracts/{contract['id']}/sign",
            headers={**auth_header(user), "Idempotency-Key": key},
            json={"document_hash": document_hash},
        )
        assert response.status_code == 200
        contract = response.get_json()
    assert contract["status"] == "ACTIVE"
    return employer, freelancer, intruder, contract


def test_progress_state_machine_is_authorized_and_idempotent(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, freelancer, intruder, contract = _active_contract_with_milestone(client)
    milestone_id = contract["version"]["milestones"][0]["id"]

    milestone = db.session.get(Milestone, uuid.UUID(milestone_id))
    assert milestone is not None
    # Money owns CREATED -> FUNDED. This seeds that boundary so Contract progress can be tested now.
    milestone.status = "FUNDED"
    db.session.commit()

    forbidden = client.post(
        f"/api/v1/milestones/{milestone_id}/start", headers=auth_header(intruder)
    )
    assert forbidden.status_code == 403

    started = client.post(
        f"/api/v1/milestones/{milestone_id}/start", headers=auth_header(freelancer)
    )
    assert started.status_code == 200
    assert started.get_json()["status"] == "IN_PROGRESS"

    submitted = client.post(
        f"/api/v1/milestones/{milestone_id}/submit",
        headers=auth_header(freelancer),
        json={"note": "first delivery"},
    )
    assert submitted.status_code == 200
    assert submitted.get_json()["status"] == "SUBMITTED"
    assert len(submitted.get_json()["events"]) == 2

    repeated = client.post(
        f"/api/v1/milestones/{milestone_id}/submit",
        headers=auth_header(freelancer),
        json={"note": "duplicate request"},
    )
    assert repeated.status_code == 200
    assert len(repeated.get_json()["events"]) == 2

    changes = client.post(
        f"/api/v1/milestones/{milestone_id}/request-changes",
        headers=auth_header(employer),
        json={"note": "Please adjust validation"},
    )
    assert changes.status_code == 200
    assert changes.get_json()["status"] == "CHANGES_REQUESTED"

    resubmitted = client.post(
        f"/api/v1/milestones/{milestone_id}/submit",
        headers=auth_header(freelancer),
        json={"note": "validation adjusted"},
    )
    assert resubmitted.status_code == 200
    assert resubmitted.get_json()["status"] == "SUBMITTED"

    approved = client.post(
        f"/api/v1/milestones/{milestone_id}/approve", headers=auth_header(employer)
    )
    assert approved.status_code == 200
    assert approved.get_json()["status"] == "APPROVED"
    assert len(approved.get_json()["events"]) == 5

    repeated_approval = client.post(
        f"/api/v1/milestones/{milestone_id}/approve", headers=auth_header(employer)
    )
    assert repeated_approval.status_code == 200
    assert len(repeated_approval.get_json()["events"]) == 5
