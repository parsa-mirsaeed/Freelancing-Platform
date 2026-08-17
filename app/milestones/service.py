from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from app.audit.service import record_audit_event
from app.contracts.models import ContractVersion
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.milestones.models import Milestone, MilestoneEvent
from app.milestones.policies import can_review_milestone, can_view_milestone, can_work_on_milestone

USER_TRANSITIONS: dict[str, set[str]] = {
    "start": {"FUNDED"},
    "submit": {"IN_PROGRESS", "CHANGES_REQUESTED"},
    "request_changes": {"SUBMITTED"},
    "approve": {"SUBMITTED"},
}


def get_milestone(milestone_id: uuid.UUID) -> Milestone:
    milestone = db.session.scalar(_milestone_query().where(Milestone.id == milestone_id))
    if milestone is None:
        raise ApiError("milestone_not_found", "Milestone not found", 404, "Milestone was not found")
    return milestone


def get_milestone_for_user(*, user: User, milestone_id: uuid.UUID) -> Milestone:
    milestone = get_milestone(milestone_id)
    contract = milestone.contract_version.contract
    if not can_view_milestone(user, contract):
        raise ApiError("forbidden", "Forbidden", 403, "Only contract parties may view milestones")
    return milestone


def start_milestone(*, user: User, milestone_id: uuid.UUID) -> Milestone:
    return _transition(
        user=user,
        milestone_id=milestone_id,
        action="start",
        target="IN_PROGRESS",
        note="",
        worker_action=True,
    )


def submit_milestone(*, user: User, milestone_id: uuid.UUID, note: str) -> Milestone:
    return _transition(
        user=user,
        milestone_id=milestone_id,
        action="submit",
        target="SUBMITTED",
        note=note,
        worker_action=True,
    )


def request_milestone_changes(*, user: User, milestone_id: uuid.UUID, note: str) -> Milestone:
    return _transition(
        user=user,
        milestone_id=milestone_id,
        action="request_changes",
        target="CHANGES_REQUESTED",
        note=note,
        worker_action=False,
    )


def approve_milestone(*, user: User, milestone_id: uuid.UUID) -> Milestone:
    return _transition(
        user=user,
        milestone_id=milestone_id,
        action="approve",
        target="APPROVED",
        note="",
        worker_action=False,
    )


def _transition(
    *,
    user: User,
    milestone_id: uuid.UUID,
    action: str,
    target: str,
    note: str,
    worker_action: bool,
) -> Milestone:
    milestone = db.session.scalar(
        _milestone_query().where(Milestone.id == milestone_id).with_for_update()
    )
    if milestone is None:
        raise ApiError("milestone_not_found", "Milestone not found", 404, "Milestone was not found")
    contract = milestone.contract_version.contract
    if contract.status != "ACTIVE":
        raise ApiError(
            "invalid_state",
            "Contract is not active",
            409,
            "Milestone progress requires an active contract",
        )
    if worker_action:
        allowed = can_work_on_milestone(user, contract)
        forbidden_detail = "Only the freelancer party may perform this milestone action"
    else:
        allowed = can_review_milestone(user, contract)
        forbidden_detail = "Only the employer party may perform this milestone action"
    if not allowed:
        raise ApiError("forbidden", "Forbidden", 403, forbidden_detail)

    if milestone.status == target:
        return get_milestone(milestone.id)
    if milestone.status not in USER_TRANSITIONS[action]:
        raise ApiError(
            "invalid_transition",
            "Invalid milestone transition",
            409,
            f"{milestone.status} cannot transition to {target}",
        )
    if action == "start":
        from app.payments.service import require_milestone_fully_funded

        require_milestone_fully_funded(milestone)

    previous = milestone.status
    milestone.status = target
    milestone.events.append(
        MilestoneEvent(
            actor_user_id=user.id,
            from_status=previous,
            to_status=target,
            note=note,
        )
    )
    record_audit_event(
        action=f"milestone.{target.lower()}",
        resource_type="milestone",
        resource_id=str(milestone.id),
        actor_user_id=user.id,
        metadata={
            "contract_id": str(contract.id),
            "from": previous,
            "to": target,
        },
    )
    db.session.commit()
    return get_milestone(milestone.id)


def _milestone_query() -> Select[tuple[Milestone]]:
    return select(Milestone).options(
        selectinload(Milestone.contract_version).selectinload(ContractVersion.contract),
        selectinload(Milestone.events),
    )
