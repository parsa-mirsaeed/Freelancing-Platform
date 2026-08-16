from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.projects.service import get_project
from app.proposals.models import Proposal, ProposalMilestone, ProposalVersion
from app.proposals.policies import can_edit_proposal, can_manage_proposal, can_submit_proposal


@dataclass(frozen=True, slots=True)
class MilestoneInput:
    title: str
    amount_minor: int
    delivery_days: int


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT": {"SUBMITTED"},
    "SUBMITTED": {"UNDER_NEGOTIATION", "WITHDRAWN", "REJECTED", "ACCEPTED"},
    "UNDER_NEGOTIATION": {"WITHDRAWN", "REJECTED", "ACCEPTED"},
    "WITHDRAWN": set(),
    "REJECTED": set(),
    "ACCEPTED": set(),
}


def get_proposal(proposal_id: uuid.UUID) -> Proposal:
    proposal = db.session.scalar(
        select(Proposal)
        .options(selectinload(Proposal.versions).selectinload(ProposalVersion.milestones))
        .where(Proposal.id == proposal_id)
    )
    if proposal is None:
        raise ApiError("proposal_not_found", "Proposal not found", 404, "Proposal was not found")
    return proposal


def list_project_proposals(*, user: User, project_id: uuid.UUID) -> list[Proposal]:
    project = get_project(project_id)
    if project.employer_user_id != user.id:
        raise ApiError(
            "forbidden",
            "Forbidden",
            403,
            "Only the project owner can compare proposals",
        )
    return list(
        db.session.scalars(
            select(Proposal)
            .options(selectinload(Proposal.versions).selectinload(ProposalVersion.milestones))
            .where(Proposal.project_id == project.id)
            .order_by(Proposal.created_at.asc())
        )
    )


def create_proposal(
    *,
    user: User,
    project_id: uuid.UUID,
    amount_minor: int,
    currency: str,
    delivery_days: int,
    cover_letter: str,
    milestones: list[MilestoneInput],
) -> Proposal:
    project = get_project(project_id)
    if not can_submit_proposal(user, project):
        raise ApiError(
            "forbidden",
            "Forbidden",
            403,
            "Proposal cannot be submitted to this project",
        )
    if project.currency is not None and project.currency != currency:
        raise ApiError(
            "validation_error",
            "Currency mismatch",
            422,
            "Proposal currency must match the project budget currency",
        )
    proposal = Proposal(project_id=project.id, freelancer_user_id=user.id, current_version=1)
    proposal.versions.append(
        _new_version(
            version_number=1,
            amount_minor=amount_minor,
            currency=currency,
            delivery_days=delivery_days,
            cover_letter=cover_letter,
            milestones=milestones,
        )
    )
    db.session.add(proposal)
    try:
        db.session.flush()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError(
            "proposal_exists",
            "Proposal already exists",
            409,
            "A freelancer may keep one versioned proposal per project",
        ) from exc
    record_audit_event(
        action="proposal.draft_created",
        resource_type="proposal",
        resource_id=str(proposal.id),
        actor_user_id=user.id,
        metadata={"project_id": str(project.id), "version": 1},
    )
    db.session.commit()
    return get_proposal(proposal.id)


def add_proposal_version(
    *,
    user: User,
    proposal_id: uuid.UUID,
    amount_minor: int,
    currency: str,
    delivery_days: int,
    cover_letter: str,
    milestones: list[MilestoneInput],
) -> Proposal:
    proposal = get_proposal(proposal_id)
    if not can_edit_proposal(user, proposal):
        raise ApiError("forbidden", "Forbidden", 403, "Proposal cannot be edited by this user")
    if proposal.status not in {"DRAFT", "UNDER_NEGOTIATION"}:
        raise ApiError(
            "invalid_transition",
            "Invalid proposal state",
            409,
            "New versions are allowed only in DRAFT or UNDER_NEGOTIATION",
        )
    current = proposal.versions[-1]
    if current.currency != currency:
        project = get_project(proposal.project_id)
        if project.currency is not None and project.currency != currency:
            raise ApiError(
                "validation_error",
                "Currency mismatch",
                422,
                "Proposal currency must match the project budget currency",
            )
    proposal.current_version += 1
    proposal.versions.append(
        _new_version(
            version_number=proposal.current_version,
            amount_minor=amount_minor,
            currency=currency,
            delivery_days=delivery_days,
            cover_letter=cover_letter,
            milestones=milestones,
        )
    )
    record_audit_event(
        action="proposal.version_created",
        resource_type="proposal",
        resource_id=str(proposal.id),
        actor_user_id=user.id,
        metadata={"version": proposal.current_version},
    )
    db.session.commit()
    return get_proposal(proposal.id)


def transition_proposal(*, user: User, proposal_id: uuid.UUID, target: str) -> Proposal:
    proposal = get_proposal(proposal_id)
    project = get_project(proposal.project_id)
    target = target.upper()
    if target not in ALLOWED_TRANSITIONS.get(proposal.status, set()):
        raise ApiError(
            "invalid_transition",
            "Invalid proposal transition",
            409,
            f"{proposal.status} cannot transition to {target}",
        )
    if target in {"SUBMITTED", "WITHDRAWN"}:
        if not can_edit_proposal(user, proposal):
            raise ApiError("forbidden", "Forbidden", 403, "Freelancer does not own this proposal")
    else:
        if not can_manage_proposal(user, proposal, project):
            raise ApiError("forbidden", "Forbidden", 403, "Employer does not own this project")
    if project.status != "OPEN":
        raise ApiError("invalid_state", "Invalid project state", 409, "Project is not open")

    previous = proposal.status
    proposal.status = target
    record_audit_event(
        action=f"proposal.{target.lower()}",
        resource_type="proposal",
        resource_id=str(proposal.id),
        actor_user_id=user.id,
        metadata={"from": previous, "to": target},
    )
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        if target == "ACCEPTED":
            raise ApiError(
                "proposal_already_accepted",
                "Project already has an accepted proposal",
                409,
                "Only one proposal can be accepted for a project",
            ) from exc
        raise
    return get_proposal(proposal.id)


def _new_version(
    *,
    version_number: int,
    amount_minor: int,
    currency: str,
    delivery_days: int,
    cover_letter: str,
    milestones: list[MilestoneInput],
) -> ProposalVersion:
    if milestones and sum(item.amount_minor for item in milestones) != amount_minor:
        raise ApiError(
            "validation_error",
            "Invalid milestones",
            422,
            "Milestone amounts must sum to the proposal amount",
        )
    version = ProposalVersion(
        version_number=version_number,
        amount_minor=amount_minor,
        currency=currency,
        delivery_days=delivery_days,
        cover_letter=cover_letter,
    )
    version.milestones.extend(
        ProposalMilestone(
            sequence=index,
            title=milestone.title,
            amount_minor=milestone.amount_minor,
            delivery_days=milestone.delivery_days,
        )
        for index, milestone in enumerate(milestones, start=1)
    )
    return version
