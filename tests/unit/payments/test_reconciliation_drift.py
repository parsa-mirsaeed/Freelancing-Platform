from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.extensions import db
from app.payments import reconciliation as reconciliation_module
from app.payments import service as payment_service
from app.payments.models import MilestoneFunding, Refund
from app.payments.providers.base import ProviderResult
from tests.helpers import auth_header
from tests.unit.payments.test_api import _active_contract_with_milestone, _capture_funding

pytestmark = pytest.mark.unit


def test_remote_capture_is_reported_without_bypassing_signed_webhook(
    client,  # type: ignore[no-untyped-def]
) -> None:
    employer, _freelancer, _project, milestone_id = _active_contract_with_milestone(
        client, suffix="reconcile-pending-payment"
    )
    created = client.post(
        f"/api/v1/milestones/{milestone_id}/fund",
        headers={**auth_header(employer), "Idempotency-Key": "reconcile-pending-payment"},
        json={"provider": "sandbox"},
    )
    assert created.status_code == 202
    intent = created.get_json()

    run = reconciliation_module.reconcile_provider("sandbox")

    assert run.status == "MISMATCH"
    assert any(
        item.get("payment_intent_id") == intent["payment_intent_id"]
        and item.get("reason") == "payment_status_mismatch"
        and item.get("provider_status") == "CAPTURED"
        for item in _discrepancies(run.details)
    )
    funding = db.session.scalar(
        select(MilestoneFunding).where(
            MilestoneFunding.payment_intent_id == uuid.UUID(intent["payment_intent_id"])
        )
    )
    assert funding is None
    financials = client.get(
        f"/api/v1/milestones/{milestone_id}/financials",
        headers=auth_header(employer),
    ).get_json()
    assert financials["milestone_status"] == "CREATED"
    assert financials["escrow_balance_minor"] == 0


def test_terminal_remote_refund_is_reported_without_reconciliation_mutation(
    client,
    monkeypatch: pytest.MonkeyPatch,  # type: ignore[no-untyped-def]
) -> None:
    employer, _freelancer, _project, milestone_id = _active_contract_with_milestone(
        client, suffix="reconcile-pending-refund"
    )
    _capture_funding(
        client,
        employer=employer,
        milestone_id=milestone_id,
        event_id="evt-reconcile-pending-refund",
        idempotency_key="fund-reconcile-pending-refund",
    )
    provider = _PendingRefundProvider()
    monkeypatch.setattr(payment_service, "get_provider", lambda _name: provider)
    monkeypatch.setattr(reconciliation_module, "get_provider", lambda _name: provider)

    refund_response = client.post(
        f"/api/v1/milestones/{milestone_id}/refund",
        headers={**auth_header(employer), "Idempotency-Key": "refund-reconcile-pending"},
        json={"provider": "sandbox"},
    )
    assert refund_response.status_code == 202
    refund_body = refund_response.get_json()
    assert refund_body["status"] == "PENDING"

    run = reconciliation_module.reconcile_provider("sandbox")

    assert run.status == "MISMATCH"
    assert any(
        item.get("refund_id") == refund_body["refund_id"]
        and item.get("reason") == "refund_status_mismatch"
        and item.get("provider_status") == "SUCCEEDED"
        for item in _discrepancies(run.details)
    )
    refund = db.session.get(Refund, uuid.UUID(refund_body["refund_id"]))
    assert refund is not None
    assert refund.status == "PENDING"
    financials = client.get(
        f"/api/v1/milestones/{milestone_id}/financials",
        headers=auth_header(employer),
    ).get_json()
    assert financials["milestone_status"] == "FUNDED"
    assert financials["escrow_balance_minor"] == 0


class _PendingRefundProvider:
    name = "sandbox"

    def refund(
        self, *, reference: str, amount_minor: int, currency: str, idempotency_key: str
    ) -> ProviderResult:
        del reference, idempotency_key
        return ProviderResult("re_pending", "PENDING", amount_minor, currency)

    def verify_refund(self, *, reference: str) -> ProviderResult:
        return ProviderResult(reference, "SUCCEEDED", 9000, "USD")

    def get_transaction(self, *, reference: str) -> ProviderResult:
        return ProviderResult(reference, "CAPTURED", 9000, "USD")


def _discrepancies(details: dict[str, object]) -> list[dict[str, object]]:
    value = details.get("discrepancies")
    assert isinstance(value, list)
    return [item for item in value if isinstance(item, dict)]
