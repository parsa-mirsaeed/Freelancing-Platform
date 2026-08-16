import pytest

from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def test_only_employer_can_create_project(client) -> None:  # type: ignore[no-untyped-def]
    freelancer = register_user(client, email="project-freelancer@example.com", role="freelancer")
    response = client.post(
        "/api/v1/projects",
        headers=auth_header(freelancer),
        json={"title": "No", "description": "No", "skills": []},
    )
    assert response.status_code == 403


def test_project_budget_requires_complete_minor_unit_range(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer = register_user(client, email="project-employer@example.com", role="employer")
    response = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={
            "title": "Project",
            "description": "Description",
            "budget_min_minor": 1000,
            "currency": "USD",
            "skills": [],
        },
    )
    assert response.status_code == 422
