from __future__ import annotations

import os
import uuid

import pytest

from app import create_app

pytestmark = pytest.mark.db


def _register(client, *, email: str, role: str):  # type: ignore[no-untyped-def]
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "role": role,
        },
    )
    assert response.status_code == 201
    return response.get_json()


def _headers(body):  # type: ignore[no-untyped-def]
    return {"Authorization": f"Bearer {body['access_token']}"}


def _app():  # type: ignore[no-untyped-def]
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "integration-secret-key",
            "SQLALCHEMY_DATABASE_URI": os.environ["DATABASE_URL"],
            "REDIS_URL": "redis://localhost:6379/15",
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_INDEX_PREFIX": "db-integration-unused",
        }
    )


def test_identity_round_trip_on_postgres() -> None:
    app = _app()
    email = f"integration-{uuid.uuid4()}@example.com"
    with app.test_client() as client:
        register = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "correct horse battery staple",
                "role": "employer",
            },
        )
        assert register.status_code == 201
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "correct horse battery staple"},
        )
        assert login.status_code == 200


def test_marketplace_round_trip_on_postgres() -> None:
    app = _app()
    suffix = uuid.uuid4()
    with app.test_client() as client:
        employer = _register(client, email=f"employer-{suffix}@example.com", role="employer")
        freelancer = _register(client, email=f"freelancer-{suffix}@example.com", role="freelancer")
        freelancer_headers = _headers(freelancer)
        employer_headers = _headers(employer)

        profile = client.put(
            "/api/v1/freelancers/me/profile",
            headers=freelancer_headers,
            json={
                "title": "Postgres Freelancer",
                "skills": ["Python", "Flask"],
                "hourly_rate_minor": 6000,
                "currency": "USD",
            },
        )
        assert profile.status_code == 200

        gig = client.post(
            "/api/v1/gigs",
            headers=freelancer_headers,
            json={
                "title": "Build an API",
                "description": "Flask and Postgres",
                "packages": [
                    {
                        "tier": "BASIC",
                        "amount_minor": 50000,
                        "currency": "USD",
                        "delivery_days": 5,
                        "revisions": 1,
                    }
                ],
            },
        )
        assert gig.status_code == 201

        project = client.post(
            "/api/v1/projects",
            headers=employer_headers,
            json={
                "title": "Marketplace API",
                "description": "Implement core domains",
                "budget_min_minor": 100000,
                "budget_max_minor": 200000,
                "currency": "USD",
                "skills": ["Python", "Flask"],
            },
        )
        assert project.status_code == 201
        project_id = project.get_json()["id"]

        proposal = client.post(
            f"/api/v1/projects/{project_id}/proposals",
            headers=freelancer_headers,
            json={
                "amount_minor": 150000,
                "currency": "USD",
                "delivery_days": 20,
                "cover_letter": "Version one",
            },
        )
        assert proposal.status_code == 201
        proposal_id = proposal.get_json()["id"]
        assert (
            client.post(
                f"/api/v1/proposals/{proposal_id}/submit", headers=freelancer_headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/proposals/{proposal_id}/negotiate", headers=employer_headers
            ).status_code
            == 200
        )
        revised = client.post(
            f"/api/v1/proposals/{proposal_id}/versions",
            headers=freelancer_headers,
            json={
                "amount_minor": 140000,
                "currency": "USD",
                "delivery_days": 15,
                "cover_letter": "Version two",
            },
        )
        assert revised.status_code == 201
        assert len(revised.get_json()["versions"]) == 2
        assert (
            client.post(
                f"/api/v1/proposals/{proposal_id}/accept", headers=employer_headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/projects/{project_id}/close", headers=employer_headers
            ).status_code
            == 200
        )
        review = client.post(
            f"/api/v1/projects/{project_id}/reviews",
            headers=employer_headers,
            json={"rating": 5, "comment": "Excellent"},
        )
        assert review.status_code == 201
