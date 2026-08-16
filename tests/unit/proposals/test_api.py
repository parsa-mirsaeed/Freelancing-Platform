import pytest

from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def _marketplace_parties(client):  # type: ignore[no-untyped-def]
    employer = register_user(client, email="proposal-employer@example.com", role="employer")
    freelancer = register_user(client, email="proposal-freelancer@example.com", role="freelancer")
    freelancer_headers = auth_header(freelancer)
    assert (
        client.put(
            "/api/v1/freelancers/me/profile",
            headers=freelancer_headers,
            json={"title": "Python Engineer", "skills": ["Python", "Flask"]},
        ).status_code
        == 200
    )
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={
            "title": "Build marketplace backend",
            "description": "Need a Flask expert",
            "budget_min_minor": 100000,
            "budget_max_minor": 200000,
            "currency": "USD",
            "skills": ["Python", "Flask"],
        },
    )
    assert project.status_code == 201
    return employer, freelancer, project.get_json()


def test_proposal_versions_are_preserved_through_negotiation(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, freelancer, project = _marketplace_parties(client)
    created = client.post(
        f"/api/v1/projects/{project['id']}/proposals",
        headers=auth_header(freelancer),
        json={
            "amount_minor": 120000,
            "currency": "USD",
            "delivery_days": 20,
            "cover_letter": "Initial offer",
            "milestones": [{"title": "API", "amount_minor": 120000, "delivery_days": 20}],
        },
    )
    assert created.status_code == 201
    proposal_id = created.get_json()["id"]

    illegal = client.post(f"/api/v1/proposals/{proposal_id}/accept", headers=auth_header(employer))
    assert illegal.status_code == 409

    submitted = client.post(
        f"/api/v1/proposals/{proposal_id}/submit", headers=auth_header(freelancer)
    )
    assert submitted.status_code == 200
    negotiated = client.post(
        f"/api/v1/proposals/{proposal_id}/negotiate", headers=auth_header(employer)
    )
    assert negotiated.status_code == 200

    version = client.post(
        f"/api/v1/proposals/{proposal_id}/versions",
        headers=auth_header(freelancer),
        json={
            "amount_minor": 140000,
            "currency": "USD",
            "delivery_days": 15,
            "cover_letter": "Negotiated offer",
        },
    )
    assert version.status_code == 201
    body = version.get_json()
    assert body["current_version"] == 2
    assert [item["amount_minor"] for item in body["versions"]] == [120000, 140000]

    accepted = client.post(f"/api/v1/proposals/{proposal_id}/accept", headers=auth_header(employer))
    assert accepted.status_code == 200
    assert accepted.get_json()["status"] == "ACCEPTED"
