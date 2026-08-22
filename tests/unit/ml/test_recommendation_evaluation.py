from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

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

pytestmark = pytest.mark.unit

_FIXTURE_PATH = Path(__file__).parents[3] / "ml" / "evaluation" / "recommendation_fixture.json"


def test_fixed_recommendation_fixture_meets_minimum_quality_and_is_deterministic() -> None:
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    project_data = fixture["project"]
    project = Project(
        id=uuid.uuid4(),
        employer_user_id=uuid.uuid4(),
        title=project_data["title"],
        description=project_data["description"],
        budget_min_minor=project_data["budget_min_minor"],
        budget_max_minor=project_data["budget_max_minor"],
        currency=project_data["currency"],
        status="OPEN",
    )
    for slug in project_data["skills"]:
        project.skill_links.append(
            ProjectSkill(
                skill=Skill(
                    id=uuid.uuid4(),
                    name=slug.title(),
                    slug=slug,
                    is_active=True,
                )
            )
        )

    first = rank_candidate_documents(
        project=project,
        documents=fixture["candidates"],
        history=fixture["history"],
    )
    second = rank_candidate_documents(
        project=project,
        documents=fixture["candidates"],
        history=fixture["history"],
    )
    assert first == second
    assert RankingConfig.from_json(DEFAULT_RANKING_CONFIG.to_json()) == DEFAULT_RANKING_CONFIG
    assert all(set(item["features"]) == EXPECTED_FEATURE_KEYS for item in first)

    ranked_ids = [item["freelancer_id"] for item in first]
    thresholds = fixture["minimum_quality"]
    assert ndcg_at_k(ranked_ids, fixture["relevance"], 4) >= thresholds["ndcg_at_4"]
    assert (
        precision_at_k(ranked_ids, set(fixture["relevant_ids"]), 3) >= thresholds["precision_at_3"]
    )
    assert recall_at_k(ranked_ids, set(fixture["relevant_ids"]), 3) >= thresholds["recall_at_3"]
    assert (
        conversion_at_k(ranked_ids, set(fixture["converted_ids"]), 1)
        >= thresholds["conversion_at_1"]
    )
