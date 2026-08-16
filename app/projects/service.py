from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.errors import ApiError
from app.extensions import db
from app.freelancers.service import (
    get_or_create_skill,
    get_profile_by_user_id,
    touch_search_projection,
)
from app.identity.models import User
from app.projects.models import Project, ProjectSkill
from app.projects.policies import can_edit_project


def list_projects() -> list[Project]:
    return list(
        db.session.scalars(
            select(Project)
            .options(selectinload(Project.skill_links).selectinload(ProjectSkill.skill))
            .where(Project.status == "OPEN")
            .order_by(Project.created_at.desc())
        )
    )


def get_project(project_id: uuid.UUID) -> Project:
    project = db.session.scalar(
        select(Project)
        .options(selectinload(Project.skill_links).selectinload(ProjectSkill.skill))
        .where(Project.id == project_id)
    )
    if project is None:
        raise ApiError("project_not_found", "Project not found", 404, "Project was not found")
    return project


def create_project(
    *,
    user: User,
    title: str,
    description: str,
    budget_min_minor: int | None,
    budget_max_minor: int | None,
    currency: str | None,
    skills: list[str],
) -> Project:
    _validate_budget(budget_min_minor, budget_max_minor, currency)
    project = Project(
        employer_user_id=user.id,
        title=title,
        description=description,
        budget_min_minor=budget_min_minor,
        budget_max_minor=budget_max_minor,
        currency=currency,
    )
    db.session.add(project)
    db.session.flush()
    _replace_skills(project, skills)
    record_audit_event(
        action="project.created",
        resource_type="project",
        resource_id=str(project.id),
        actor_user_id=user.id,
    )
    db.session.commit()
    return get_project(project.id)


def update_project(
    *,
    user: User,
    project_id: uuid.UUID,
    title: str,
    description: str,
    budget_min_minor: int | None,
    budget_max_minor: int | None,
    currency: str | None,
    skills: list[str],
) -> Project:
    project = get_project(project_id)
    if not can_edit_project(user, project):
        raise ApiError("forbidden", "Forbidden", 403, "Project cannot be edited by this user")
    if project.status != "OPEN":
        raise ApiError(
            "invalid_state",
            "Invalid project state",
            409,
            "Only OPEN projects can be edited",
        )
    _validate_budget(budget_min_minor, budget_max_minor, currency)
    project.title = title
    project.description = description
    project.budget_min_minor = budget_min_minor
    project.budget_max_minor = budget_max_minor
    project.currency = currency
    _replace_skills(project, skills)
    record_audit_event(
        action="project.updated",
        resource_type="project",
        resource_id=str(project.id),
        actor_user_id=user.id,
    )
    db.session.commit()
    return get_project(project.id)


def close_project(*, user: User, project_id: uuid.UUID) -> Project:
    from app.proposals.models import Proposal

    project = get_project(project_id)
    if not can_edit_project(user, project):
        raise ApiError("forbidden", "Forbidden", 403, "Project cannot be closed by this user")
    if project.status != "OPEN":
        raise ApiError(
            "invalid_state",
            "Invalid project state",
            409,
            "Only OPEN projects can close",
        )
    accepted = db.session.scalar(
        select(Proposal).where(Proposal.project_id == project.id, Proposal.status == "ACCEPTED")
    )
    if accepted is None:
        raise ApiError(
            "invalid_state",
            "Project cannot close",
            409,
            "A project needs an accepted proposal before it can close",
        )
    project.status = "CLOSED"
    profile = get_profile_by_user_id(accepted.freelancer_user_id)
    touch_search_projection(profile)
    record_audit_event(
        action="project.closed",
        resource_type="project",
        resource_id=str(project.id),
        actor_user_id=user.id,
    )
    db.session.commit()
    return project


def _validate_budget(minimum: int | None, maximum: int | None, currency: str | None) -> None:
    provided = [minimum is not None, maximum is not None, currency is not None]
    if any(provided) and not all(provided):
        raise ApiError(
            "validation_error",
            "Invalid budget",
            422,
            "budget_min_minor, budget_max_minor, and currency must be provided together",
        )
    if minimum is not None and maximum is not None and (minimum < 0 or maximum < minimum):
        raise ApiError("validation_error", "Invalid budget", 422, "Budget range is invalid")


def _replace_skills(project: Project, values: list[str]) -> None:
    project.skill_links.clear()
    seen: set[uuid.UUID] = set()
    for value in values:
        skill = get_or_create_skill(value)
        if skill.id in seen:
            continue
        seen.add(skill.id)
        project.skill_links.append(ProjectSkill(skill_id=skill.id))
