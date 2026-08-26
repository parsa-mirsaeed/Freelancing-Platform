from __future__ import annotations

from celery import shared_task

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
    return {
        "reconciliation_run_id": str(run.id),
        "provider": run.provider,
        "status": run.status,
        "checked_count": run.checked_count,
        "discrepancy_count": run.discrepancy_count,
    }
