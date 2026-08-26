from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from app.common.http import optional_string, parse_uuid
from app.errors import ApiError
from app.identity.auth import require_roles
from app.identity.models import User
from app.payments.actions import get_payment_action
from app.payments.providers.registry import get_provider
from app.payments.service import (
    fund_milestone,
    get_milestone_financial_state,
    process_provider_webhook,
    refund_milestone,
    release_milestone,
)

payments_bp = Blueprint("payments", __name__, url_prefix="/api/v1")


@payments_bp.get("/milestones/<milestone_id>/financials")
@require_roles("freelancer", "employer")
def get_milestone_financials(milestone_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    body = get_milestone_financial_state(
        user=user, milestone_id=parse_uuid(milestone_id, "milestone_id")
    )
    return jsonify(body)


@payments_bp.post("/milestones/<milestone_id>/fund")
@require_roles("employer")
def post_milestone_fund(milestone_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ApiError("validation_error", "Invalid request", 422, "Request body must be an object")
    provider = optional_string(payload, "provider", max_length=40) or str(
        current_app.config["PAYMENT_DEFAULT_PROVIDER"]
    )
    body, status = fund_milestone(
        user=user,
        milestone_id=parse_uuid(milestone_id, "milestone_id"),
        provider_name=provider,
        idempotency_key=_idempotency_key(),
    )
    return jsonify(body), status


@payments_bp.get("/payment-intents/<payment_intent_id>/action")
@require_roles("employer")
def get_payment_intent_action(payment_intent_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    body = get_payment_action(
        user=user,
        payment_intent_id=parse_uuid(payment_intent_id, "payment_intent_id"),
    )
    return jsonify(body)


@payments_bp.post("/milestones/<milestone_id>/release")
@require_roles("employer")
def post_milestone_release(milestone_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    body, status = release_milestone(
        user=user,
        milestone_id=parse_uuid(milestone_id, "milestone_id"),
        idempotency_key=_idempotency_key(),
    )
    return jsonify(body), status


@payments_bp.post("/milestones/<milestone_id>/refund")
@require_roles("employer")
def post_milestone_refund(milestone_id: str):  # type: ignore[no-untyped-def]
    user: User = g.current_user
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ApiError("validation_error", "Invalid request", 422, "Request body must be an object")
    provider = optional_string(payload, "provider", max_length=40) or str(
        current_app.config["PAYMENT_DEFAULT_PROVIDER"]
    )
    body, status = refund_milestone(
        user=user,
        milestone_id=parse_uuid(milestone_id, "milestone_id"),
        provider_name=provider,
        idempotency_key=_idempotency_key(),
    )
    return jsonify(body), status


@payments_bp.post("/payments/webhooks/<provider_name>")
def post_payment_webhook(provider_name: str):  # type: ignore[no-untyped-def]
    payload = request.get_data(cache=False)
    provider = get_provider(provider_name)
    signature = request.headers.get(provider.webhook_signature_header, "")
    body, status = process_provider_webhook(
        provider_name=provider_name, payload=payload, signature=signature
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
