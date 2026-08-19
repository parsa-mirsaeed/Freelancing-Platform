from __future__ import annotations

import math
import uuid
from collections.abc import Sequence

from sqlalchemy import select

from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.projects.models import Project, ProjectSkill
from app.proposals.models import Proposal, ProposalVersion

PRICE_MODEL_VERSION = "pricing-baseline-v1"
PRICE_FEATURE_VERSION = "pricing-history-v1"


def estimate_project_price(*, user: User, project_id: uuid.UUID) -> dict[str, object]:
    project = db.session.get(Project, project_id)
    if project is None:
        raise ApiError("project_not_found", "Project not found", 404, "Project was not found")
    if project.employer_user_id != user.id:
        raise ApiError("forbidden", "Forbidden", 403, "You do not own this project")
    if project.currency is None:
        return _response(
            project=project,
            lower=None,
            upper=None,
            sample_count=0,
            method="insufficient_data",
        )

    skill_ids = [link.skill_id for link in project.skill_links]
    statement = (
        select(ProposalVersion.amount_minor)
        .join(Proposal, Proposal.id == ProposalVersion.proposal_id)
        .join(Project, Project.id == Proposal.project_id)
        .where(
            Proposal.project_id != project.id,
            Proposal.status.in_(("SUBMITTED", "UNDER_NEGOTIATION", "ACCEPTED", "REJECTED")),
            ProposalVersion.version_number == Proposal.current_version,
            ProposalVersion.currency == project.currency,
        )
    )
    if skill_ids:
        statement = (
            statement.join(ProjectSkill, ProjectSkill.project_id == Project.id)
            .where(ProjectSkill.skill_id.in_(skill_ids))
            .distinct()
        )
    samples = sorted(int(value) for value in db.session.scalars(statement))
    if len(samples) >= 3:
        lower = _percentile(samples, 0.25)
        upper = _percentile(samples, 0.75)
        return _response(
            project=project,
            lower=lower,
            upper=max(lower, upper),
            sample_count=len(samples),
            method="historical_proposal_iqr",
        )
    if project.budget_min_minor is not None and project.budget_max_minor is not None:
        return _response(
            project=project,
            lower=project.budget_min_minor,
            upper=project.budget_max_minor,
            sample_count=len(samples),
            method="project_budget_fallback",
        )
    return _response(
        project=project,
        lower=None,
        upper=None,
        sample_count=len(samples),
        method="insufficient_data",
    )


def _percentile(values: Sequence[int], fraction: float) -> int:
    if not values:
        raise ValueError("values cannot be empty")
    position = (len(values) - 1) * fraction
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return int(values[lower_index])
    weight = position - lower_index
    interpolated = values[lower_index] * (1 - weight) + values[upper_index] * weight
    return int(round(interpolated))


def _response(
    *,
    project: Project,
    lower: int | None,
    upper: int | None,
    sample_count: int,
    method: str,
) -> dict[str, object]:
    if sample_count >= 10:
        confidence = "MEDIUM"
    elif sample_count >= 3:
        confidence = "LOW"
    elif method == "project_budget_fallback":
        confidence = "BUDGET_ONLY"
    else:
        confidence = "INSUFFICIENT"
    return {
        "project_id": str(project.id),
        "model_version": PRICE_MODEL_VERSION,
        "feature_version": PRICE_FEATURE_VERSION,
        "currency": project.currency,
        "lower_minor": lower,
        "upper_minor": upper,
        "sample_count": sample_count,
        "confidence": confidence,
        "method": method,
    }
