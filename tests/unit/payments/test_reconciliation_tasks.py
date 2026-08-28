from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from app.celery import create_celery_app
from app.payments import tasks

pytestmark = pytest.mark.unit


def _app(*, enabled: bool, provider: str = "stripe") -> Flask:
    app = Flask(__name__)
    app.config.update(
        REDIS_URL="redis://localhost:6379/15",
        PAYMENT_RUNTIME_ENABLED=enabled,
        PAYMENT_DEFAULT_PROVIDER=provider,
    )
    return app


def test_reconciliation_tasks_use_isolated_queue_and_periodic_schedule() -> None:
    celery_app = create_celery_app(_app(enabled=False))

    routes = celery_app.conf.task_routes
    assert routes["payments.reconcile_provider"] == {"queue": "reconciliation"}
    assert routes["payments.reconcile_default_provider"] == {"queue": "reconciliation"}
    assert routes["payments.*"] == {"queue": "payments"}

    schedule = celery_app.conf.beat_schedule["reconcile-default-payment-provider"]
    assert schedule["task"] == "payments.reconcile_default_provider"
    assert schedule["schedule"] == 300.0


def test_periodic_reconciliation_is_inert_when_payment_runtime_is_disabled() -> None:
    app = _app(enabled=False)
    with app.app_context():
        result = tasks.reconcile_default_provider_task.run()

    assert result == {
        "provider": "stripe",
        "status": "DISABLED",
        "checked_count": 0,
        "discrepancy_count": 0,
    }


def test_periodic_reconciliation_uses_backend_default_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _app(enabled=True)
    run = SimpleNamespace(
        id="run-1",
        provider="stripe",
        status="SUCCEEDED",
        checked_count=4,
        discrepancy_count=0,
    )
    observed: list[str] = []

    def fake_reconcile(provider_name: str) -> object:
        observed.append(provider_name)
        return run

    monkeypatch.setattr(tasks, "reconcile_provider", fake_reconcile)
    with app.app_context():
        result = tasks.reconcile_default_provider_task.run()

    assert observed == ["stripe"]
    assert result == {
        "reconciliation_run_id": "run-1",
        "provider": "stripe",
        "status": "SUCCEEDED",
        "checked_count": 4,
        "discrepancy_count": 0,
    }
