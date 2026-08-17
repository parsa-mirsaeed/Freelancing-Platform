from __future__ import annotations

import pytest

from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def test_contract_without_explicit_proposal_milestones_gets_full_delivery_milestone(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer = register_user(client, email="default-ms-employer@example.com", role="employer")
    freelancer = register_user(client, email="default-ms-freelancer@example.com", role="freelancer")
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={"title": "Whole contract", "description": "One delivery", "skills": []},
    ).get_json()
    proposal = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json={
            "amount_minor": 12500,
            "currency": "USD",
            "delivery_days": 7,
            "cover_letter": "Single delivery",
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

    response = client.get(
        f"/api/v1/projects/{project['id']}/contract", headers=auth_header(employer)
    )
    assert response.status_code == 200
    contract = response.get_json()
    milestones = contract["version"]["milestones"]
    snapshot_milestones = contract["version"]["snapshot"]["milestones"]
    assert len(milestones) == len(snapshot_milestones) == 1
    assert milestones[0]["title"] == "Full contract delivery"
    assert milestones[0]["amount_minor"] == 12500
    assert milestones[0]["currency"] == "USD"
    assert milestones[0]["delivery_days"] == 7
    assert snapshot_milestones[0]["amount_minor"] == 12500
