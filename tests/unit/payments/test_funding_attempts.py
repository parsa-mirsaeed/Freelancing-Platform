from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.extensions import db
from app.payments.models import PaymentIntent
from tests.helpers import auth_header, register_user
from tests.unit.payments.test_api import _active_contract_with_milestone

pytestmark = pytest.mark.unit


def test_new_idempotency_key_reuses_active_milestone_funding_attempt(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, _freelancer, _project, milestone_id = _active_contract_with_milestone(
        client,
        suffix="single-active-funding",
    )

    first = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": "fund-attempt-1"},
        json={"provider": "sandbox"},
    )
    second = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": "fund-attempt-2"},
        json={"provider": "sandbox"},
    )

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.get_json()["payment_intent_id"] == first.get_json()["payment_intent_id"]
    assert second.get_json()["provider_reference"] == first.get_json()["provider_reference"]
    pending = list(
        db.session.scalars(
            select(PaymentIntent).where(
                PaymentIntent.milestone_id == uuid.UUID(milestone_id),
                PaymentIntent.status == "PENDING",
            )
        )
    )
    assert len(pending) == 1


def test_payment_runtime_kill_switch_fails_closed_before_provider_call(
    client,
    app,
) -> None:  # type: ignore[no-untyped-def]
    employer, _freelancer, _project, milestone_id = _active_contract_with_milestone(
        client,
        suffix="payment-runtime-disabled",
    )
    app.config["PAYMENT_RUNTIME_ENABLED"] = False

    response = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": "disabled-funding"},
        json={"provider": "sandbox"},
    )

    assert response.status_code == 503
    assert response.get_json()["type"] == "payment_runtime_disabled"
    assert db.session.scalar(
        select(PaymentIntent).where(PaymentIntent.milestone_id == uuid.UUID(milestone_id))
    ) is None


def test_payment_action_is_visible_only_to_the_employer_that_created_it(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, _freelancer, _project, milestone_id = _active_contract_with_milestone(
        client,
        suffix="payment-action-owner",
    )
    other_employer = register_user(
        client,
        email="payment-action-other@example.com",
        role="employer",
    )
    created = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": "payment-action-owner"},
        json={"provider": "sandbox"},
    )
    assert created.status_code == 202
    payment_intent_id = created.get_json()["payment_intent_id"]

    denied = client.get(
        f"/api/v1/payment-intents/{payment_intent_id}/action",
        headers=auth_header(other_employer),
    )
    assert denied.status_code == 403

    allowed = client.get(
        f"/api/v1/payment-intents/{payment_intent_id}/action",
        headers=auth_header(employer),
    )
    assert allowed.status_code == 200
    assert allowed.get_json()["action"] is None
