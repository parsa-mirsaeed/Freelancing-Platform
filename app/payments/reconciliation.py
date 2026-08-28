from __future__ import annotations

from sqlalchemy import select

from app.audit.service import record_audit_event
from app.common.outbox import enqueue_outbox_event
from app.extensions import db
from app.payments.models import PaymentIntent, ReconciliationRun, Refund
from app.payments.providers.registry import get_provider
from app.payments.service import reconcile_provider as reconcile_captured_provider


def reconcile_provider(provider_name: str) -> ReconciliationRun:
    pending_checked, pending_discrepancies = _inspect_pending_provider_state(provider_name)
    run = reconcile_captured_provider(provider_name)
    existing_discrepancies = _existing_discrepancies(run)
    combined = [*existing_discrepancies, *pending_discrepancies]

    run.checked_count += pending_checked
    run.discrepancy_count = len(combined)
    run.details = {"discrepancies": combined}
    run.status = "MISMATCH" if combined else "SUCCEEDED"

    if pending_discrepancies:
        enqueue_outbox_event(
            event_type="payments.reconciliation_pending_mismatch",
            aggregate_type="reconciliation_run",
            aggregate_id=str(run.id),
            payload={
                "provider": run.provider,
                "count": len(pending_discrepancies),
            },
        )
    record_audit_event(
        action="payments.pending_reconciled",
        resource_type="reconciliation_run",
        resource_id=str(run.id),
        metadata={
            "provider": run.provider,
            "checked_count": pending_checked,
            "discrepancy_count": len(pending_discrepancies),
        },
    )
    db.session.commit()
    return run


def _inspect_pending_provider_state(
    provider_name: str,
) -> tuple[int, list[dict[str, object]]]:
    provider = get_provider(provider_name)
    checked_count = 0
    discrepancies: list[dict[str, object]] = []

    intents = list(
        db.session.scalars(
            select(PaymentIntent).where(
                PaymentIntent.provider == provider.name,
                PaymentIntent.status == "PENDING",
            )
        )
    )
    for intent in intents:
        checked_count += 1
        if intent.provider_reference is None:
            discrepancies.append(
                {
                    "payment_intent_id": str(intent.id),
                    "reason": "pending_payment_missing_reference",
                }
            )
            continue
        remote = provider.get_transaction(reference=intent.provider_reference)
        if remote.amount_minor != intent.amount_minor or remote.currency != intent.currency:
            discrepancies.append(
                {
                    "payment_intent_id": str(intent.id),
                    "provider_reference": intent.provider_reference,
                    "reason": "pending_payment_provider_mismatch",
                }
            )
            continue
        if remote.status != "PENDING":
            discrepancies.append(
                {
                    "payment_intent_id": str(intent.id),
                    "provider_reference": intent.provider_reference,
                    "reason": "payment_status_mismatch",
                    "local_status": intent.status,
                    "provider_status": remote.status,
                }
            )

    refunds = list(
        db.session.scalars(
            select(Refund).where(
                Refund.provider == provider.name,
                Refund.status == "PENDING",
                Refund.provider_reference.is_not(None),
            )
        )
    )
    for refund in refunds:
        checked_count += 1
        provider_reference = refund.provider_reference
        if provider_reference is None:
            continue
        remote = provider.verify_refund(reference=provider_reference)
        if remote.amount_minor != refund.amount_minor or remote.currency != refund.currency:
            discrepancies.append(
                {
                    "refund_id": str(refund.id),
                    "provider_reference": provider_reference,
                    "reason": "pending_refund_provider_mismatch",
                }
            )
            continue
        if remote.status != "PENDING":
            discrepancies.append(
                {
                    "refund_id": str(refund.id),
                    "provider_reference": provider_reference,
                    "reason": "refund_status_mismatch",
                    "local_status": refund.status,
                    "provider_status": remote.status,
                }
            )

    return checked_count, discrepancies


def _existing_discrepancies(run: ReconciliationRun) -> list[dict[str, object]]:
    value = run.details.get("discrepancies")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
