from __future__ import annotations

import uuid

from flask import Blueprint, current_app, g, jsonify, request

from app.common.http import (
    optional_string,
    require_currency,
    require_int,
    require_json_object,
    require_string,
)
from app.errors import ApiError
from app.identity.auth import require_recent_mfa, require_roles
from app.identity.models import User
from app.payouts.provider_accounts import (
    configure_payout_provider_account,
    disable_payout_provider_account,
)
from app.payouts.service import create_payout

payouts_bp = Blueprint("payouts", __name__, url_prefix="/api/v1")


@payouts_bp.post("/payouts")
@require_roles("freelancer")
def post_payout():  # type: ignore[no-untyped-def]
    user: User = g.current_user
    require_recent_mfa()
    payload = require_json_object(request)
    provider = optional_string(payload, "provider", max_length=40) or str(
        current_app.config["PAYMENT_DEFAULT_PROVIDER"]
    )
    body, status = create_payout(
        user=user,
        amount_minor=require_int(payload, "amount_minor", minimum=1),
        currency=require_currency(payload),
        provider_name=provider,
        idempotency_key=_idempotency_key(),
    )
    return jsonify(body), status


@payouts_bp.put(
    "/admin/freelancers/<uuid:freelancer_user_id>/payout-provider-accounts/<provider_name>"
)
@require_roles("admin")
def put_payout_provider_account(
    freelancer_user_id: uuid.UUID, provider_name: str
):  # type: ignore[no-untyped-def]
    administrator: User = g.current_user
    payload = require_json_object(request)
    body = configure_payout_provider_account(
        administrator=administrator,
        freelancer_user_id=freelancer_user_id,
        provider_name=provider_name,
        external_account_reference=require_string(
            payload,
            "external_account_reference",
            max_length=255,
        ),
    )
    return jsonify(body)


@payouts_bp.delete(
    "/admin/freelancers/<uuid:freelancer_user_id>/payout-provider-accounts/<provider_name>"
)
@require_roles("admin")
def delete_payout_provider_account(
    freelancer_user_id: uuid.UUID, provider_name: str
):  # type: ignore[no-untyped-def]
    administrator: User = g.current_user
    body = disable_payout_provider_account(
        administrator=administrator,
        freelancer_user_id=freelancer_user_id,
        provider_name=provider_name,
    )
    return jsonify(body)


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
