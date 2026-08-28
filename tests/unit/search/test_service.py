import uuid

import pytest
from sqlalchemy import select

from app.common.models import OutboxEvent
from app.extensions import db
from app.freelancers.service import SEARCH_REFRESH_EVENT, get_profile_by_user_id
from app.search.service import build_freelancer_document
from app.search.tasks import drain_search_outbox
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


def test_search_index_failure_preserves_postgres_state_and_retry_intent(
    client,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    freelancer = register_user(client, email="search-failure@example.com", role="freelancer")
    user_id = uuid.UUID(freelancer["user"]["id"])
    response = client.put(
        "/api/v1/freelancers/me/profile",
        headers=auth_header(freelancer),
        json={
            "title": "Durable Search Profile",
            "bio": "PostgreSQL remains authoritative",
            "accepting_work": True,
            "skills": ["Python"],
        },
    )
    assert response.status_code == 200

    def fail_index(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("elasticsearch unavailable")

    monkeypatch.setattr("app.search.tasks.index_freelancer", fail_index)
    with pytest.raises(RuntimeError, match="elasticsearch unavailable"):
        drain_search_outbox()

    db.session.expire_all()
    profile = get_profile_by_user_id(user_id)
    assert profile.title == "Durable Search Profile"
    pending = db.session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.event_type == SEARCH_REFRESH_EVENT,
            OutboxEvent.aggregate_id == str(user_id),
        )
    )
    assert pending is not None
    assert pending.published_at is None

    monkeypatch.setattr("app.search.tasks.index_freelancer", lambda *_args, **_kwargs: None)
    assert drain_search_outbox() == 1
    db.session.expire_all()
    published = db.session.get(OutboxEvent, pending.id)
    assert published is not None
    assert published.published_at is not None
