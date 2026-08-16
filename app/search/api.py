from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.common.http import ValidationError
from app.search.service import search_freelancers

search_bp = Blueprint("search", __name__, url_prefix="/api/v1/search")


@search_bp.get("/freelancers")
def get_freelancer_search():  # type: ignore[no-untyped-def]
    query = request.args.get("q", type=str)
    skills = [item.strip() for item in request.args.getlist("skill") if item.strip()]
    available = _parse_optional_bool(request.args.get("available"))
    limit = request.args.get("limit", default=20, type=int)
    if limit is None or limit < 1 or limit > 50:
        raise ValidationError("limit must be an integer from 1 to 50")
    return jsonify(
        {
            "items": search_freelancers(
                query=query.strip() if query and query.strip() else None,
                skills=skills,
                available=available,
                limit=limit,
            )
        }
    )


def _parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    raise ValidationError("available must be true or false")
