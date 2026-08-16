from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.common.http import (
    optional_currency,
    optional_int,
    parse_uuid,
    require_json_object,
    require_string,
    require_string_list,
)
from app.identity.auth import require_roles
from app.identity.models import User
from app.projects.models import Project, ProjectSkill
from app.projects.service import (
    close_project,
    create_project,
    get_project,
    list_projects,
    update_project,
)

projects_bp = Blueprint("projects", __name__, url_prefix="/api/v1/projects")


@projects_bp.get("")
def get_projects():  # type: ignore[no-untyped-def]
    return jsonify({"items": [_serialize_project(project) for project in list_projects()]})


@projects_bp.get("/<project_id>")
def get_project_detail(project_id: str):  # type: ignore[no-untyped-def]
    return jsonify(_serialize_project(get_project(parse_uuid(project_id, "project_id"))))


@projects_bp.post("")
@require_roles("employer")
def post_project():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    project = create_project(
        user=user,
        title=require_string(payload, "title", max_length=180),
        description=require_string(payload, "description"),
        budget_min_minor=optional_int(payload, "budget_min_minor", minimum=0),
        budget_max_minor=optional_int(payload, "budget_max_minor", minimum=0),
        currency=optional_currency(payload),
        skills=require_string_list(payload, "skills", max_items=50, item_max_length=80),
    )
    return jsonify(_serialize_project(project)), 201


@projects_bp.put("/<project_id>")
@require_roles("employer")
def put_project(project_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    project = update_project(
        user=user,
        project_id=parse_uuid(project_id, "project_id"),
        title=require_string(payload, "title", max_length=180),
        description=require_string(payload, "description"),
        budget_min_minor=optional_int(payload, "budget_min_minor", minimum=0),
        budget_max_minor=optional_int(payload, "budget_max_minor", minimum=0),
        currency=optional_currency(payload),
        skills=require_string_list(payload, "skills", max_items=50, item_max_length=80),
    )
    return jsonify(_serialize_project(project))


@projects_bp.post("/<project_id>/close")
@require_roles("employer")
def post_close_project(project_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    return jsonify(_serialize_project(close_project(user=user, project_id=parse_uuid(project_id))))


def _serialize_project(project: Project) -> dict[str, object]:
    return {
        "id": str(project.id),
        "employer_user_id": str(project.employer_user_id),
        "title": project.title,
        "description": project.description,
        "budget_min_minor": project.budget_min_minor,
        "budget_max_minor": project.budget_max_minor,
        "currency": project.currency,
        "status": project.status,
        "skills": [_skill_name(link) for link in project.skill_links],
    }


def _skill_name(link: ProjectSkill) -> str:
    return link.skill.name
