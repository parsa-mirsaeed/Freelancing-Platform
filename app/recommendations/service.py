from __future__ import annotations

import hashlib
import json
import statistics
import uuid
from collections.abc import Sequence
from typing import Any, TypedDict

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.projects.models import Project
from app.proposals.models import Proposal, ProposalVersion
from app.recommendations.features import DEFAULT_RANKING_CONFIG, FEATURE_VERSION, MODEL_VERSION
from app.recommendations.models import (
    ModelRegistryEntry,
    RecommendationEvent,
    RecommendationPrediction,
    RecommendationRun,
)
from app.recommendations.registry import ensure_matching_model
from app.search.service import search_freelancers

_CLIENT_EVENT_TYPES = {"IMPRESSION", "PROFILE_VIEW"}


class RankedCandidate(TypedDict):
    freelancer_id: str
    score_basis_points: int
    features: dict[str, float]
    reasons: list[str]


def recommend_for_project(*, user: User, project_id: uuid.UUID, limit: int) -> dict[str, object]:
    project = _owned_open_project(user=user, project_id=project_id)
    skill_slugs = [link.skill.slug for link in project.skill_links]
    query_text = f"{project.title} {project.description[:400]}".strip()
    candidate_limit = min(50, max(20, limit * 5))
    documents = search_freelancers(
        query=query_text,
        skills=skill_slugs,
        available=True,
        limit=candidate_limit,
    )
    documents = [
        document for document in documents if str(document.get("freelancer_id", "")) != str(user.id)
    ]
    model = ensure_matching_model()
    history = _historical_proposal_amounts(project=project, documents=documents)
    ranked = rank_candidate_documents(project=project, documents=documents, history=history)
    selected = ranked[:limit]
    candidate_set_version = _candidate_set_version(project=project, documents=documents)
    run = RecommendationRun(
        id=uuid.uuid4(),
        project_id=project.id,
        employer_user_id=user.id,
        model_version_id=model.id,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        candidate_set_version=candidate_set_version,
    )
    db.session.add(run)
    predictions: list[RecommendationPrediction] = []
    for rank, item in enumerate(selected, start=1):
        prediction_features: dict[str, object] = {
            key: value for key, value in item["features"].items()
        }
        prediction = RecommendationPrediction(
            run_id=run.id,
            freelancer_user_id=uuid.UUID(item["freelancer_id"]),
            rank=rank,
            score_basis_points=item["score_basis_points"],
            model_version=MODEL_VERSION,
            feature_version=FEATURE_VERSION,
            candidate_set_version=candidate_set_version,
            features_json=prediction_features,
            reasons_json=item["reasons"].copy(),
        )
        db.session.add(prediction)
        predictions.append(prediction)
    db.session.commit()
    return {
        "run_id": str(run.id),
        "project_id": str(project.id),
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "candidate_set_version": candidate_set_version,
        "items": [
            {
                "freelancer_id": str(prediction.freelancer_user_id),
                "rank": prediction.rank,
                "score": round(prediction.score_basis_points / 10000, 4),
                "score_basis_points": prediction.score_basis_points,
                "features": prediction.features_json,
                "reasons": prediction.reasons_json,
            }
            for prediction in predictions
        ],
    }


def rank_candidate_documents(
    *,
    project: Project,
    documents: Sequence[dict[str, object]],
    history: dict[str, list[int]],
) -> list[RankedCandidate]:
    project_skills = {link.skill.slug for link in project.skill_links}
    ranked: list[RankedCandidate] = []
    seen: set[str] = set()
    for document in documents:
        freelancer_id = str(document.get("freelancer_id", ""))
        if not freelancer_id or freelancer_id in seen:
            continue
        seen.add(freelancer_id)
        candidate_skills = {
            str(skill) for skill in _as_list(document.get("skills")) if str(skill).strip()
        }
        if project_skills:
            skill_match = len(project_skills & candidate_skills) / len(project_skills)
        else:
            skill_match = 0.5
        completed_jobs = max(0, _as_int(document.get("completed_jobs")))
        experience = min(1.0, completed_jobs / 10)
        rating = _as_float(document.get("rating"))
        reputation = min(1.0, max(0.0, rating / 5)) if rating is not None else 0.5
        availability = 1.0 if bool(document.get("availability")) else 0.0
        price_fit = _price_fit(
            amounts=history.get(freelancer_id, []),
            budget_min=project.budget_min_minor,
            budget_max=project.budget_max_minor,
        )
        features = {
            "skill_match": round(skill_match, 4),
            "experience": round(experience, 4),
            "price_fit": round(price_fit, 4),
            "availability": availability,
            "reputation": round(reputation, 4),
        }
        score = DEFAULT_RANKING_CONFIG.score_basis_points(features)
        reasons = _reasons(
            skill_match=skill_match,
            completed_jobs=completed_jobs,
            rating=rating,
            price_history=history.get(freelancer_id, []),
            available=bool(document.get("availability")),
        )
        ranked.append(
            {
                "freelancer_id": freelancer_id,
                "score_basis_points": score,
                "features": features,
                "reasons": reasons,
            }
        )
    ranked.sort(key=lambda item: (-item["score_basis_points"], item["freelancer_id"]))
    return ranked


def record_client_event(
    *,
    user: User,
    run_id: uuid.UUID,
    freelancer_user_id: uuid.UUID,
    event_type: str,
    client_event_id: str,
) -> tuple[RecommendationEvent, bool]:
    normalized_type = event_type.strip().upper()
    normalized_client_id = client_event_id.strip()
    if normalized_type not in _CLIENT_EVENT_TYPES:
        raise ApiError(
            "validation_error",
            "Invalid recommendation event",
            422,
            "Clients may record only IMPRESSION or PROFILE_VIEW events",
        )
    if not normalized_client_id or len(normalized_client_id) > 80:
        raise ApiError(
            "validation_error",
            "Invalid client event id",
            422,
            "client_event_id must be between 1 and 80 characters",
        )
    run = db.session.get(RecommendationRun, run_id)
    if run is None:
        raise ApiError("run_not_found", "Recommendation run not found", 404, "Run was not found")
    if run.employer_user_id != user.id:
        raise ApiError("forbidden", "Forbidden", 403, "Only the run owner may record events")
    prediction = db.session.scalar(
        select(RecommendationPrediction).where(
            RecommendationPrediction.run_id == run.id,
            RecommendationPrediction.freelancer_user_id == freelancer_user_id,
        )
    )
    if prediction is None:
        raise ApiError(
            "candidate_not_found",
            "Candidate was not in this run",
            404,
            "Recommendation events must reference a predicted candidate",
        )
    existing = db.session.scalar(
        select(RecommendationEvent).where(
            RecommendationEvent.actor_user_id == user.id,
            RecommendationEvent.client_event_id == normalized_client_id,
        )
    )
    if existing is not None:
        if (
            existing.run_id != run.id
            or existing.freelancer_user_id != freelancer_user_id
            or existing.event_type != normalized_type
        ):
            raise ApiError(
                "client_event_id_reused",
                "Client event id reused",
                409,
                "client_event_id was already used for different event content",
            )
        return existing, False

    event = RecommendationEvent(
        run_id=run.id,
        freelancer_user_id=freelancer_user_id,
        actor_user_id=user.id,
        client_event_id=normalized_client_id,
        event_type=normalized_type,
    )
    try:
        with db.session.begin_nested():
            db.session.add(event)
            db.session.flush()
    except IntegrityError as exc:
        existing = db.session.scalar(
            select(RecommendationEvent).where(
                RecommendationEvent.actor_user_id == user.id,
                RecommendationEvent.client_event_id == normalized_client_id,
            )
        )
        if existing is None:
            raise
        if (
            existing.run_id != run.id
            or existing.freelancer_user_id != freelancer_user_id
            or existing.event_type != normalized_type
        ):
            raise ApiError(
                "client_event_id_reused",
                "Client event id reused",
                409,
                "client_event_id was concurrently reused for different event content",
            ) from exc
        return existing, False
    db.session.commit()
    return event, True


def serialize_model(entry: ModelRegistryEntry) -> dict[str, Any]:
    return {
        "id": str(entry.id),
        "name": entry.name,
        "version": entry.version,
        "model_type": entry.model_type,
        "feature_version": entry.feature_version,
        "status": entry.status,
        "config": entry.config_json,
        "metrics": entry.metrics_json,
        "artifact_uri": entry.artifact_uri,
        "created_at": entry.created_at.isoformat(),
    }


def _owned_open_project(*, user: User, project_id: uuid.UUID) -> Project:
    project = db.session.get(Project, project_id)
    if project is None:
        raise ApiError("project_not_found", "Project not found", 404, "Project was not found")
    if project.employer_user_id != user.id:
        raise ApiError("forbidden", "Forbidden", 403, "You do not own this project")
    if project.status != "OPEN":
        raise ApiError(
            "invalid_state",
            "Project is not open",
            409,
            "Recommendations are generated only for open projects",
        )
    return project


def _historical_proposal_amounts(
    *, project: Project, documents: Sequence[dict[str, object]]
) -> dict[str, list[int]]:
    if project.currency is None:
        return {}
    candidate_ids = []
    for document in documents:
        try:
            candidate_ids.append(uuid.UUID(str(document.get("freelancer_id", ""))))
        except ValueError:
            continue
    if not candidate_ids:
        return {}
    rows = db.session.execute(
        select(Proposal.freelancer_user_id, ProposalVersion.amount_minor)
        .join(ProposalVersion, ProposalVersion.proposal_id == Proposal.id)
        .where(
            Proposal.freelancer_user_id.in_(candidate_ids),
            Proposal.project_id != project.id,
            Proposal.status.in_(("SUBMITTED", "UNDER_NEGOTIATION", "ACCEPTED", "REJECTED")),
            ProposalVersion.version_number == Proposal.current_version,
            ProposalVersion.currency == project.currency,
        )
    )
    result: dict[str, list[int]] = {}
    for freelancer_user_id, amount_minor in rows:
        result.setdefault(str(freelancer_user_id), []).append(int(amount_minor))
    return result


def _price_fit(*, amounts: Sequence[int], budget_min: int | None, budget_max: int | None) -> float:
    if budget_min is None or budget_max is None or not amounts:
        return 0.5
    typical = float(statistics.median(amounts))
    if budget_min <= typical <= budget_max:
        return 1.0
    if typical < budget_min:
        distance = budget_min - typical
        scale = max(float(budget_min), 1.0)
    else:
        distance = typical - budget_max
        scale = max(float(budget_max), 1.0)
    return max(0.0, 1.0 - distance / scale)


def _candidate_set_version(*, project: Project, documents: Sequence[dict[str, object]]) -> str:
    ids = sorted(str(document.get("freelancer_id", "")) for document in documents)
    payload = json.dumps(
        {
            "project_id": str(project.id),
            "project_updated_at": project.updated_at.isoformat(),
            "ids": ids,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _reasons(
    *,
    skill_match: float,
    completed_jobs: int,
    rating: float | None,
    price_history: Sequence[int],
    available: bool,
) -> list[str]:
    reasons = [f"skill_overlap={skill_match:.2f}"]
    if completed_jobs:
        reasons.append(f"completed_jobs={completed_jobs}")
    if rating is not None:
        reasons.append(f"review_score={rating:.2f}")
    reasons.append("price_history=available" if price_history else "price_history=insufficient")
    reasons.append("availability=accepting_work" if available else "availability=unavailable")
    return reasons


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None
