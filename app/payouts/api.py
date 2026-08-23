from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from app.common.http import require_currency, require_int, require_json_object, require_string
from app.errors import ApiError
from app.identity.auth import require_recent_mfa, require_roles
from app.identity.models import User
from app.payouts.service import create_payout

payouts_bp = Blueprint("payouts", __name__, url_prefix="/api/v1")


@payouts_bp.post("/payouts")
@require_roles("freelancer")
def post_payout():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    require_recent_mfa()
    payload = require_json_object(request)
    body, status = create_payout(
        user=user,
        amount_minor=require_int(payload, "amount_minor", minimum=1),
        currency=require_currency(payload),
        provider_name=require_string(payload, "provider", max_length=40),
        idempotency_key=_idempotency_key(),
    )
    return jsonify(body), status


def _idempotency_key() -> str:
    value = request.headers.get("Idempotency-Key")
    if value is None:
        raise ApiError(
            "idempotency_key_required",
            "Idempotency key required",
            400,
            "Idempotency-Key header is required for financial mutations",
        )
    return value
