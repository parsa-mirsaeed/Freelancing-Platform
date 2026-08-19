from __future__ import annotations

import os
import uuid

import pytest

from app import create_app
from app.extensions import db, elasticsearch_extension
from app.search.tasks import drain_search_outbox
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.search


def test_freelancer_projection_is_searchable_and_recommendable() -> None:
    prefix = f"freelancing-ci-{uuid.uuid4()}"
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "search-integration-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
            "REDIS_URL": "redis://localhost:6379/15",
            "ELASTICSEARCH_URL": os.environ["ELASTICSEARCH_URL"],
            "ELASTICSEARCH_INDEX_PREFIX": prefix,
        }
    )
    with app.app_context():
        db.create_all()
        try:
            with app.test_client() as client:
                freelancer = register_user(
                    client,
                    email=f"search-{uuid.uuid4()}@example.com",
                    role="freelancer",
                )
                freelancer_headers = auth_header(freelancer)
                profile = client.put(
                    "/api/v1/freelancers/me/profile",
                    headers=freelancer_headers,
                    json={
                        "title": "Flask Search Specialist",
                        "bio": "PostgreSQL and API architecture",
                        "skills": ["Python", "Flask"],
                        "accepting_work": True,
                    },
                )
                assert profile.status_code == 200
                assert drain_search_outbox(refresh=True) == 1

                search = client.get(
                    "/api/v1/search/freelancers?q=Flask&skill=python&available=true"
                )
                assert search.status_code == 200
                items = search.get_json()["items"]
                assert len(items) == 1
                assert items[0]["freelancer_id"] == freelancer["user"]["id"]
                assert items[0]["projection_version"] == profile.get_json()["projection_version"]

                employer = register_user(
                    client,
                    email=f"recommend-{uuid.uuid4()}@example.com",
                    role="employer",
                )
                project = client.post(
                    "/api/v1/projects",
                    headers=auth_header(employer),
                    json={
                        "title": "Flask API project",
                        "description": "Build a Python Flask backend",
                        "skills": ["Python", "Flask"],
                        "budget_min_minor": 80000,
                        "budget_max_minor": 120000,
                        "currency": "USD",
                    },
                ).get_json()
                recommendation = client.get(
                    f"/api/v1/projects/{project['id']}/recommendations?limit=5",
                    headers=auth_header(employer),
                )
                assert recommendation.status_code == 200
                recommendation_body = recommendation.get_json()
                assert recommendation_body["model_version"] == "rule-v1"
                assert recommendation_body["feature_version"] == "matching-features-v1"
                assert recommendation_body["items"][0]["freelancer_id"] == freelancer["user"]["id"]
                assert recommendation_body["items"][0]["features"]["skill_match"] == 1.0

                event_payload = {
                    "freelancer_user_id": freelancer["user"]["id"],
                    "event_type": "IMPRESSION",
                    "client_event_id": "recommendation-impression-1",
                }
                first_event = client.post(
                    f"/api/v1/recommendations/{recommendation_body['run_id']}/events",
                    headers=auth_header(employer),
                    json=event_payload,
                )
                retry_event = client.post(
                    f"/api/v1/recommendations/{recommendation_body['run_id']}/events",
                    headers=auth_header(employer),
                    json=event_payload,
                )
                assert first_event.status_code == 201
                assert retry_event.status_code == 200
                assert first_event.get_json()["id"] == retry_event.get_json()["id"]
        finally:
            client = elasticsearch_extension.get_client()
            client.indices.delete(index=f"{prefix}-freelancers-v1", ignore_unavailable=True)
            db.session.remove()
            db.drop_all()
