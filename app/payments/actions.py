from __future__ import annotations

import uuid

from app.errors import ApiError
from app.extensions import db
from app.identity.models import User
from app.payments.models import PaymentIntent
from app.payments.providers.registry import get_provider


def get_payment_action(*, user: User, payment_intent_id: uuid.UUID) -> dict[str, object]:
    intent = db.session.get(PaymentIntent, payment_intent_id)
    if intent is None:
        raise ApiError(
            "payment_not_found",
            "Payment not found",
            404,
            "Payment intent was not found",
        )
    if intent.employer_user_id != user.id:
        raise ApiError(
            "forbidden",
            "Forbidden",
            403,
            "Only the employer that created the payment may retrieve its payment action",
        )
    if intent.provider_reference is None:
        raise RuntimeError("Payment intent is missing its provider reference")

    provider = get_provider(intent.provider)
    action = provider.get_payment_action(reference=intent.provider_reference)
    return {
        "payment_intent_id": str(intent.id),
        "provider": intent.provider,
        "status": intent.status,
        "action": (
            None
            if action is None
            else {
                "kind": action.kind,
                "client_secret": action.client_secret,
                "publishable_key": action.publishable_key,
            }
        ),
    }
