from __future__ import annotations

import os
import uuid

import pytest

from app import create_app

pytestmark = pytest.mark.db


def test_identity_round_trip_on_postgres() -> None:
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "integration-secret-key",
            "SQLALCHEMY_DATABASE_URI": os.environ["DATABASE_URL"],
            "REDIS_URL": "redis://localhost:6379/15",
        }
    )
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
