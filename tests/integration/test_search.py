from __future__ import annotations

import os
import uuid

import pytest

from app import create_app
from app.extensions import db, elasticsearch_extension
from app.search.tasks import drain_search_outbox

pytestmark = pytest.mark.search


def test_freelancer_projection_is_searchable() -> None:
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
                registered = client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": f"search-{uuid.uuid4()}@example.com",
                        "password": "correct horse battery staple",
                        "role": "freelancer",
                    },
                ).get_json()
                headers = {"Authorization": f"Bearer {registered['access_token']}"}
                profile = client.put(
                    "/api/v1/freelancers/me/profile",
                    headers=headers,
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
                assert items[0]["freelancer_id"] == registered["user"]["id"]
                assert items[0]["projection_version"] == profile.get_json()["projection_version"]
        finally:
            client = elasticsearch_extension.get_client()
            client.indices.delete(index=f"{prefix}-freelancers-v1", ignore_unavailable=True)
            db.session.remove()
            db.drop_all()
