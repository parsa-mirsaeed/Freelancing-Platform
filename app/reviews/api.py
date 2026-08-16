from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.common.http import optional_string, parse_uuid, require_int, require_json_object
from app.identity.auth import require_roles
from app.identity.models import User
from app.reviews.models import Review
from app.reviews.service import create_review, list_reviews

reviews_bp = Blueprint("reviews", __name__, url_prefix="/api/v1")


@reviews_bp.post("/projects/<project_id>/reviews")
@require_roles("employer")
def post_review(project_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    review = create_review(
        user=user,
        project_id=parse_uuid(project_id, "project_id"),
        rating=require_int(payload, "rating", minimum=1, maximum=5),
        comment=optional_string(payload, "comment") or "",
    )
    return jsonify(_serialize_review(review)), 201


@reviews_bp.get("/freelancers/<user_id>/reviews")
def get_reviews(user_id: str):  # type: ignore[no-untyped-def]
    return jsonify(
        {
            "items": [
                _serialize_review(review) for review in list_reviews(parse_uuid(user_id, "user_id"))
            ]
        }
    )


def _serialize_review(review: Review) -> dict[str, object]:
    return {
        "id": str(review.id),
        "project_id": str(review.project_id),
        "reviewer_user_id": str(review.reviewer_user_id),
        "freelancer_user_id": str(review.freelancer_user_id),
        "rating": review.rating,
        "comment": review.comment,
        "created_at": review.created_at.isoformat(),
    }
