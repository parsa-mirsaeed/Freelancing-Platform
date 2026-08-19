from __future__ import annotations

import uuid

import pytest

from app.extensions import db
from app.freelancers.models import Skill
from app.projects.models import Project, ProjectSkill
from app.recommendations.evaluation import (
    conversion_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from app.recommendations.features import (
    DEFAULT_RANKING_CONFIG,
    EXPECTED_FEATURE_KEYS,
    RankingConfig,
)
from app.recommendations.service import rank_candidate_documents
from app.recommendations.skills import suggest_skills
from tests.helpers import auth_header, register_user

pytestmark = pytest.mark.unit


def _project() -> Project:
    project = Project(
        id=uuid.uuid4(),
        employer_user_id=uuid.uuid4(),
        title="Python API",
        description="Build a Flask API",
        budget_min_minor=80000,
        budget_max_minor=120000,
        currency="USD",
        status="OPEN",
    )
    project.skill_links.append(
        ProjectSkill(skill=Skill(id=uuid.uuid4(), name="Python", slug="python", is_active=True))
    )
    project.skill_links.append(
        ProjectSkill(skill=Skill(id=uuid.uuid4(), name="Flask", slug="flask", is_active=True))
    )
    return project


def test_ranking_config_serialization_and_tiny_ndcg_regression() -> None:
    encoded = DEFAULT_RANKING_CONFIG.to_json()
    assert RankingConfig.from_json(encoded) == DEFAULT_RANKING_CONFIG

    project = _project()
    documents: list[dict[str, object]] = [
        {
            "freelancer_id": "00000000-0000-4000-8000-000000000001",
            "skills": ["python", "flask"],
            "completed_jobs": 8,
            "rating": 4.9,
            "availability": True,
        },
        {
            "freelancer_id": "00000000-0000-4000-8000-000000000002",
            "skills": ["python"],
            "completed_jobs": 3,
            "rating": 4.2,
            "availability": True,
        },
        {
            "freelancer_id": "00000000-0000-4000-8000-000000000003",
            "skills": ["flask"],
            "completed_jobs": 0,
            "rating": 3.5,
            "availability": True,
        },
    ]
    first_id = str(documents[0]["freelancer_id"])
    second_id = str(documents[1]["freelancer_id"])
    third_id = str(documents[2]["freelancer_id"])
    history = {
        first_id: [90000, 100000, 110000],
        second_id: [150000],
    }
    ranked = rank_candidate_documents(project=project, documents=documents, history=history)
    ranked_ids = [str(item["freelancer_id"]) for item in ranked]
    assert ranked_ids[0] == first_id
    assert set(ranked[0]["features"]) == EXPECTED_FEATURE_KEYS
    relevance = {first_id: 3.0, second_id: 2.0, third_id: 0.0}
    assert ndcg_at_k(ranked_ids, relevance, 3) >= 0.95
    relevant = {first_id, second_id}
    assert precision_at_k(ranked_ids, relevant, 2) == 1.0
    assert recall_at_k(ranked_ids, relevant, 2) == 1.0
    assert conversion_at_k(ranked_ids, {first_id}, 1) == 1.0


def test_skill_suggestions_do_not_mutate_profile(client, app) -> None:  # type: ignore[no-untyped-def]
    freelancer = register_user(
        client,
        email="skill-suggestion@example.com",
        role="freelancer",
    )
    response = client.put(
        "/api/v1/freelancers/me/profile",
        headers=auth_header(freelancer),
        json={
            "title": "Django API Developer",
            "bio": "Python backend systems",
            "skills": ["Python"],
            "accepting_work": True,
        },
    )
    assert response.status_code == 200
    with app.app_context():
        db.session.add(Skill(name="Django", slug="django", is_active=True))
        db.session.commit()
        from app.identity.models import User

        user = db.session.get(User, uuid.UUID(freelancer["user"]["id"]))
        assert user is not None
        result = suggest_skills(user=user)
        assert result["profile_mutated"] is False
        suggestions = result["suggestions"]
        assert isinstance(suggestions, list)
        assert any(item["slug"] == "django" for item in suggestions)

    profile_after = client.get(
        "/api/v1/freelancers/me/profile",
        headers=auth_header(freelancer),
    ).get_json()
    assert profile_after["skills"] == ["Python"]


def test_price_estimate_returns_budget_interval_without_false_precision(client) -> None:  # type: ignore[no-untyped-def]
    employer = register_user(
        client,
        email="price-estimate@example.com",
        role="employer",
    )
    project = client.post(
        "/api/v1/projects",
        headers=auth_header(employer),
        json={
            "title": "API pricing",
            "description": "Need a backend",
            "skills": [],
            "budget_min_minor": 80000,
            "budget_max_minor": 120000,
            "currency": "USD",
        },
    ).get_json()
    response = client.get(
        f"/api/v1/projects/{project['id']}/ai/price-estimate",
        headers=auth_header(employer),
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["lower_minor"] == 80000
    assert body["upper_minor"] == 120000
    assert body["method"] == "project_budget_fallback"
    assert "point_estimate_minor" not in body
