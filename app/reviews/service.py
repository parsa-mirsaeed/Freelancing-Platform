from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.audit.service import record_audit_event
from app.contracts.models import Contract
from app.errors import ApiError
from app.extensions import db
from app.freelancers.service import get_profile_by_user_id, touch_search_projection
from app.identity.models import User
from app.projects.service import get_project
from app.reviews.models import Review


def create_review(*, user: User, project_id: uuid.UUID, rating: int, comment: str) -> Review:
    project = get_project(project_id)
    if project.employer_user_id != user.id:
        raise ApiError("forbidden", "Forbidden", 403, "Only the project owner can review")
    if project.status != "CLOSED":
        raise ApiError(
            "review_not_eligible",
            "Review not available",
            409,
            "The project must be closed before a review is created",
        )
    contract = db.session.scalar(select(Contract).where(Contract.project_id == project.id))
    if contract is None or contract.status != "ACTIVE":
        raise ApiError(
            "review_not_eligible",
            "Review not available",
            409,
            "A completed active contract is required before review",
        )
    review = Review(
        project_id=project.id,
        reviewer_user_id=user.id,
        freelancer_user_id=contract.freelancer_user_id,
        rating=rating,
        comment=comment,
    )
    db.session.add(review)
    try:
        db.session.flush()
    except IntegrityError as exc:
        db.session.rollback()
        raise ApiError(
            "review_exists",
            "Review already exists",
            409,
            "This project has already been reviewed",
        ) from exc
    profile = get_profile_by_user_id(contract.freelancer_user_id)
    touch_search_projection(profile)
    record_audit_event(
        action="review.created",
        resource_type="review",
        resource_id=str(review.id),
        actor_user_id=user.id,
        metadata={"project_id": str(project.id), "contract_id": str(contract.id), "rating": rating},
    )
    db.session.commit()
    return review


def list_reviews(freelancer_user_id: uuid.UUID) -> list[Review]:
    return list(
        db.session.scalars(
            select(Review)
            .where(Review.freelancer_user_id == freelancer_user_id)
            .order_by(Review.created_at.desc())
        )
    )
