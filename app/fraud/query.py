from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select

from app.errors import ApiError
from app.extensions import db
from app.fraud.models import RiskAssessment
from app.fraud.service import serialize_assessment

REVIEW_STATUSES = frozenset({"NOT_REQUIRED", "PENDING", "CLEARED", "ESCALATED"})


def list_assessments(
    *,
    after: uuid.UUID | None,
    limit: int,
    review_status: str | None,
) -> dict[str, object]:
    if limit < 1 or limit > 100:
        raise ApiError(
            "validation_error",
            "Invalid limit",
            422,
            "limit must be between 1 and 100",
        )

    normalized_status = review_status.strip().upper() if review_status else None
    if normalized_status and normalized_status not in REVIEW_STATUSES:
        raise ApiError(
            "validation_error",
            "Invalid review status",
            422,
            "status must be NOT_REQUIRED, PENDING, CLEARED, or ESCALATED",
        )

    statement = select(RiskAssessment)
    if normalized_status:
        statement = statement.where(RiskAssessment.review_status == normalized_status)

    if after is not None:
        cursor = db.session.get(RiskAssessment, after)
        if cursor is None:
            raise ApiError(
                "validation_error",
                "Invalid assessment cursor",
                422,
                "after must reference an existing risk assessment",
            )
        statement = statement.where(
            or_(
                RiskAssessment.created_at < cursor.created_at,
                and_(
                    RiskAssessment.created_at == cursor.created_at,
                    RiskAssessment.id < cursor.id,
                ),
            )
        )

    rows = list(
        db.session.scalars(
            statement.order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc()).limit(
                limit + 1
            )
        )
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    return {
        "items": [serialize_assessment(item) for item in visible],
        "next_after": str(visible[-1].id) if has_more and visible else None,
    }
