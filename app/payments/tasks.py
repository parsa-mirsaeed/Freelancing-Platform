from __future__ import annotations

from celery import shared_task
from flask import current_app

from app.payments.providers.base import ProviderTemporaryError
from app.payments.service import reconcile_provider


@shared_task(
    name="payments.reconcile_provider",
    autoretry_for=(ProviderTemporaryError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)  # type: ignore[untyped-decorator]
def reconcile_provider_task(provider_name: str) -> dict[str, object]:
    run = reconcile_provider(provider_name)
    return _serialize_reconciliation_run(run)


@shared_task(
    name="payments.reconcile_default_provider",
    autoretry_for=(ProviderTemporaryError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)  # type: ignore[untyped-decorator]
def reconcile_default_provider_task() -> dict[str, object]:
    if not current_app.config["PAYMENT_RUNTIME_ENABLED"]:
        return {
            "provider": current_app.config["PAYMENT_DEFAULT_PROVIDER"],
            "status": "DISABLED",
            "checked_count": 0,
            "discrepancy_count": 0,
        }
    run = reconcile_provider(current_app.config["PAYMENT_DEFAULT_PROVIDER"])
    return _serialize_reconciliation_run(run)


def _serialize_reconciliation_run(run: object) -> dict[str, object]:
    return {
        "reconciliation_run_id": str(getattr(run, "id")),
        "provider": getattr(run, "provider"),
        "status": getattr(run, "status"),
        "checked_count": getattr(run, "checked_count"),
        "discrepancy_count": getattr(run, "discrepancy_count"),
    }
