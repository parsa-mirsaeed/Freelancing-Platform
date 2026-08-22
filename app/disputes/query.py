from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.disputes.models import DISPUTE_STATES, Dispute, DisputeParty
from app.disputes.service import serialize_dispute
from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.milestones.models import Milestone


def list_disputes_for_user(
    *,
    user: User,
    after: uuid.UUID | None,
    limit: int,
    status: str | None,
) -> tuple[list[Dispute], uuid.UUID | None]:
    if limit < 1 or limit > 100:
        raise ApiError(
            "validation_error",
            "Invalid pagination",
            422,
            "limit must be between 1 and 100",
        )

    normalized_status = status.strip().upper() if status else None
    if normalized_status and normalized_status not in DISPUTE_STATES:
        raise ApiError(
            "validation_error",
            "Invalid dispute status",
            422,
            "status must be a valid dispute state",
        )

    statement = _visible_disputes(user)
    if normalized_status:
        statement = statement.where(Dispute.status == normalized_status)

    if after is not None:
        cursor = db.session.scalar(_visible_disputes(user).where(Dispute.id == after))
        if cursor is None:
            raise ApiError(
                "validation_error",
                "Invalid pagination",
                422,
                "after must identify a visible dispute",
            )
        statement = statement.where(
            or_(
                Dispute.created_at < cursor.created_at,
                and_(Dispute.created_at == cursor.created_at, Dispute.id < cursor.id),
            )
        )

    statement = statement.order_by(Dispute.created_at.desc(), Dispute.id.desc()).limit(limit + 1)
    rows = list(db.session.scalars(statement).unique())
    has_more = len(rows) > limit
    items = rows[:limit]
    next_after = items[-1].id if has_more and items else None
    return items, next_after


def serialize_dispute_case(dispute: Dispute) -> dict[str, object]:
    payload = serialize_dispute(dispute)
    milestone = db.session.get(Milestone, dispute.milestone_id)
    if milestone is None:
        raise ApiError(
            "milestone_not_found",
            "Milestone not found",
            404,
            "The dispute milestone no longer exists",
        )
    payload["milestone"] = {
        "id": str(milestone.id),
        "sequence": milestone.sequence,
        "title": milestone.title,
        "amount_minor": milestone.amount_minor,
        "currency": milestone.currency,
        "status": milestone.status,
    }
    return payload


def _visible_disputes(user: User):  # type: ignore[no-untyped-def]
    statement = select(Dispute).options(
        selectinload(Dispute.parties),
        selectinload(Dispute.evidence),
        selectinload(Dispute.events),
        selectinload(Dispute.decision),
    )
    if any(assignment.role == "admin" for assignment in user.roles):
        return statement
    return statement.join(
        DisputeParty,
        DisputeParty.dispute_id == Dispute.id,
    ).where(DisputeParty.user_id == user.id)
