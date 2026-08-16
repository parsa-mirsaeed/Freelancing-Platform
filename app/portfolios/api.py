from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.common.http import optional_string, parse_uuid, require_json_object, require_string
from app.identity.auth import require_roles
from app.identity.models import User
from app.portfolios.models import PortfolioItem
from app.portfolios.service import create_portfolio_item, delete_portfolio_item, list_portfolio

portfolios_bp = Blueprint("portfolios", __name__, url_prefix="/api/v1")


@portfolios_bp.get("/freelancers/<user_id>/portfolio")
def get_portfolio(user_id: str):  # type: ignore[no-untyped-def]
    return jsonify(
        {
            "items": [
                _serialize_item(item) for item in list_portfolio(parse_uuid(user_id, "user_id"))
            ]
        }
    )


@portfolios_bp.post("/freelancers/me/portfolio")
@require_roles("freelancer")
def post_portfolio_item():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = require_json_object(request)
    item = create_portfolio_item(
        user=user,
        title=require_string(payload, "title", max_length=160),
        description=optional_string(payload, "description") or "",
        external_url=optional_string(payload, "external_url", max_length=2048),
    )
    return jsonify(_serialize_item(item)), 201


@portfolios_bp.delete("/portfolio/<item_id>")
@require_roles("freelancer")
def delete_item(item_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    delete_portfolio_item(user=user, item_id=parse_uuid(item_id, "item_id"))
    return "", 204


def _serialize_item(item: PortfolioItem) -> dict[str, object]:
    return {
        "id": str(item.id),
        "title": item.title,
        "description": item.description,
        "external_url": item.external_url,
        "files": [
            {
                "id": str(file.id),
                "mime_type": file.mime_type,
                "file_size_bytes": file.file_size_bytes,
                "scan_status": file.scan_status,
            }
            for file in item.files
            if file.scan_status == "SAFE"
        ],
    }
