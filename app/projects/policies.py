from __future__ import annotations

from app.identity.models import User
from app.projects.models import Project


def can_edit_project(user: User, project: Project) -> bool:
    return project.employer_user_id == user.id and any(
        role.role == "employer" for role in user.roles
    )
