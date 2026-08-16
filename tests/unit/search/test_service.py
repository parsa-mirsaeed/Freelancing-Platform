import uuid

import pytest

from app.freelancers.service import get_profile_by_user_id
from app.search.service import build_freelancer_document
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def test_search_document_is_projection_of_postgres_state(
    client,  # type: ignore[no-untyped-def]
) -> None:
    freelancer = register_user(client, email="search-doc@example.com", role="freelancer")
    headers = auth_header(freelancer)
    response = client.put(
        "/api/v1/freelancers/me/profile",
        headers=headers,
        json={
            "title": "Flask Engineer",
            "bio": "PostgreSQL APIs",
            "hourly_rate_minor": 5000,
            "currency": "USD",
            "accepting_work": True,
            "languages": ["en"],
            "skills": ["Python", "Flask"],
        },
    )
    assert response.status_code == 200
    profile = get_profile_by_user_id(uuid.UUID(response.get_json()["user_id"]))
    document = build_freelancer_document(profile)
    assert document["freelancer_id"] == response.get_json()["user_id"]
    assert set(document["skills"]) == {"python", "flask"}
    assert document["hourly_rate_minor"] == 5000
    assert document["availability"] is True
