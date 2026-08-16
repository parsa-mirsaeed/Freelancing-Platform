import pytest
from sqlalchemy import select

from app.common.models import OutboxEvent
from app.extensions import db
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def test_profile_skills_and_availability_create_outbox_events(
    client,  # type: ignore[no-untyped-def]
) -> None:
    freelancer = register_user(client, email="freelancer-profile@example.com", role="freelancer")
    headers = auth_header(freelancer)

    response = client.put(
        "/api/v1/freelancers/me/profile",
        headers=headers,
        json={
            "title": "Senior Flask Engineer",
            "bio": "APIs and PostgreSQL",
            "hourly_rate_minor": 4500,
            "currency": "USD",
            "timezone": "Europe/Zurich",
            "accepting_work": True,
            "languages": ["en", "fa", "en"],
            "skills": ["Python", "Flask", "python"],
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["hourly_rate_minor"] == 4500
    assert body["currency"] == "USD"
    assert set(body["skills"]) == {"Python", "Flask"}
    assert body["languages"] == ["en", "fa"]

    rules = client.put(
        "/api/v1/freelancers/me/availability/rules",
        headers=headers,
        json={
            "rules": [
                {
                    "weekday": 1,
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "timezone": "Europe/Zurich",
                }
            ]
        },
    )
    assert rules.status_code == 200
    assert rules.get_json()["rules"][0]["start_time"] == "09:00"

    exception = client.put(
        "/api/v1/freelancers/me/availability/exceptions",
        headers=headers,
        json={"date": "2026-08-20", "available": False, "reason": "Unavailable"},
    )
    assert exception.status_code == 200
    assert exception.get_json()["available"] is False

    outbox = list(db.session.scalars(select(OutboxEvent)))
    assert len(outbox) == 3
    assert all(event.event_type == "search.freelancer.refresh" for event in outbox)


def test_profile_rejects_partial_money_pair(client) -> None:  # type: ignore[no-untyped-def]
    freelancer = register_user(client, email="money-pair@example.com", role="freelancer")
    response = client.put(
        "/api/v1/freelancers/me/profile",
        headers=auth_header(freelancer),
        json={"title": "Engineer", "hourly_rate_minor": 1000, "skills": []},
    )
    assert response.status_code == 422

    currency_only = client.put(
        "/api/v1/freelancers/me/profile",
        headers=auth_header(freelancer),
        json={"title": "Engineer", "currency": "USD", "skills": []},
    )
    assert currency_only.status_code == 422
