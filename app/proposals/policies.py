from __future__ import annotations

from app.identity.models import User
from app.projects.models import Project
from app.proposals.models import Proposal


def can_submit_proposal(user: User, project: Project) -> bool:
    return (
        project.status == "OPEN"
        and project.employer_user_id != user.id
        and any(role.role == "freelancer" for role in user.roles)
    )


def can_edit_proposal(user: User, proposal: Proposal) -> bool:
    return proposal.freelancer_user_id == user.id


def can_manage_proposal(user: User, proposal: Proposal, project: Project) -> bool:
    return proposal.project_id == project.id and project.employer_user_id == user.id
