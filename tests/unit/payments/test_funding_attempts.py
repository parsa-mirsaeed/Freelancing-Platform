from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.extensions import db
from app.payments.models import PaymentIntent
from tests.helpers import auth_header
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
