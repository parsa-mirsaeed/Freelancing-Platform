from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import create_app
from app.extensions import db
from app.identity.models import UserRole
from app.recommendations.models import ModelRegistryEntry
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.db


def _app():  # type: ignore[no-untyped-def]
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "ai-postgres-integration-secret-key",
            "SQLALCHEMY_DATABASE_URI": os.environ["DATABASE_URL"],
            "REDIS_URL": "redis://localhost:6379/15",
            "ELASTICSEARCH_URL": "http://localhost:9200",
            "ELASTICSEARCH_INDEX_PREFIX": "ai-db-integration-unused",
        }
    )


def test_model_registry_seed_and_active_version_constraint() -> None:
    app = _app()
    with app.app_context():
        names = {
            model.name
            for model in db.session.scalars(
                select(ModelRegistryEntry).where(ModelRegistryEntry.status == "ACTIVE")
            )
        }
        assert {
            "freelancer_matching",
            "skill_extraction",
            "price_estimation",
            "fraud_risk",
        }.issubset(names)

        db.session.add(
            ModelRegistryEntry(
                name="freelancer_matching",
                version=f"conflicting-{uuid.uuid4()}",
                model_type="ML",
                feature_version="matching-features-v2",
                status="ACTIVE",
                config_json={},
                metrics_json={"ndcg_at_10": 0.9},
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_risk_review_and_price_interval_persist_on_postgres() -> None:
    app = _app()
    suffix = str(uuid.uuid4())
    with app.test_client() as client:
        admin = register_user(
            client,
            email=f"ai-admin-{suffix}@example.com",
            role="employer",
        )
        subject = register_user(
            client,
            email=f"ai-subject-{suffix}@example.com",
            role="freelancer",
        )
        employer = register_user(
            client,
            email=f"ai-price-{suffix}@example.com",
            role="employer",
        )
        with app.app_context():
            db.session.add(UserRole(user_id=uuid.UUID(admin["user"]["id"]), role="admin"))
            db.session.commit()

        assessed = client.post(
            "/api/v1/admin/risk/assessments",
            headers=auth_header(admin),
            json={
                "subject_user_id": subject["user"]["id"],
                "text": "Contact me on Telegram https://one.example https://two.example https://three.example",
            },
        )
        assert assessed.status_code == 201
        assessment = assessed.get_json()
        reviewed = client.post(
            f"/api/v1/admin/risk/assessments/{assessment['id']}/review",
            headers=auth_header(admin),
            json={"decision": "CLEAR", "note": "Reviewed against account context"},
        )
        assert reviewed.status_code == 200
        assert reviewed.get_json()["review_status"] == "CLEARED"

        project = client.post(
            "/api/v1/projects",
            headers=auth_header(employer),
            json={
                "title": "Postgres price estimate",
                "description": "Budget-backed interval",
                "skills": [],
                "budget_min_minor": 50000,
                "budget_max_minor": 90000,
                "currency": "USD",
            },
        ).get_json()
        estimate = client.get(
            f"/api/v1/projects/{project['id']}/ai/price-estimate",
            headers=auth_header(employer),
        )
        assert estimate.status_code == 200
        assert estimate.get_json()["method"] == "project_budget_fallback"
