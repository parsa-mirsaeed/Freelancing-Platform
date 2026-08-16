from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import create_app
from app.contracts.models import ContractVersion
from app.extensions import db

pytestmark = pytest.mark.db


def _app():  # type: ignore[no-untyped-def]
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "contract-integration-secret-key",
            "SQLALCHEMY_DATABASE_URI": os.environ["DATABASE_URL"],
            "REDIS_URL": "redis://localhost:6379/15",
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_INDEX_PREFIX": "contract-db-integration-unused",
        }
    )


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


def test_contract_snapshot_signatures_and_database_immutability_on_postgres() -> None:
    app = _app()
    suffix = uuid.uuid4()
    with app.test_client() as client:
        employer = _register(
            client, email=f"contract-employer-{suffix}@example.com", role="employer"
        )
        freelancer = _register(
            client, email=f"contract-freelancer-{suffix}@example.com", role="freelancer"
        )
        project = client.post(
            "/api/v1/projects",
            headers=_headers(employer),
            json={"title": "DB Contract", "description": "Frozen scope", "skills": []},
        ).get_json()
        proposal = client.post(
            f"/api/v1/projects/{project['id']}/proposals",
            headers=_headers(freelancer),
            json={
                "amount_minor": 25000,
                "currency": "USD",
                "delivery_days": 5,
                "milestones": [{"title": "Delivery", "amount_minor": 25000, "delivery_days": 5}],
            },
        ).get_json()
        assert (
            client.post(
                f"/api/v1/proposals/{proposal['id']}/submit", headers=_headers(freelancer)
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/proposals/{proposal['id']}/accept", headers=_headers(employer)
            ).status_code
            == 200
        )

        contract = client.get(
            f"/api/v1/projects/{project['id']}/contract", headers=_headers(employer)
        ).get_json()
        version = contract["version"]
        assert version["snapshot"]["milestones"][0]["amount_minor"] == 25000
        assert version["milestones"][0]["amount_minor"] == 25000
        document_hash = version["document_hash"]

        for key, user in (
            (f"db-employer-{suffix}", employer),
            (f"db-freelancer-{suffix}", freelancer),
        ):
            signed = client.post(
                f"/api/v1/contracts/{contract['id']}/sign",
                headers={**_headers(user), "Idempotency-Key": key},
                json={"document_hash": document_hash},
            )
            assert signed.status_code == 200
            contract = signed.get_json()
        assert contract["status"] == "ACTIVE"
        assert len(contract["version"]["signatures"]) == 2
        version_id = contract["version"]["id"]

    with app.app_context():
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE contract_versions "
                    "SET document_hash = :document_hash "
                    "WHERE id = CAST(:version_id AS uuid)"
                ),
                {"document_hash": "0" * 64, "version_id": version_id},
            )
        persisted = db.session.get(ContractVersion, uuid.UUID(version_id))
        assert persisted is not None
        assert persisted.document_hash == document_hash
