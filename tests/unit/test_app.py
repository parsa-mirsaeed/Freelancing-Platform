from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

import pytest

from app.config import Settings
from app.extensions import db
from app.feature_flags import is_feature_enabled
from app.observability import JsonFormatter, increment_counter, observe_histogram
from app.payments.models import ProviderEvent, ReconciliationRun

pytestmark = pytest.mark.unit


def test_live_health_is_dependency_free(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]
    assert len(response.headers["X-Trace-ID"]) == 32


def test_unknown_route_uses_standard_error(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/does-not-exist", headers={"X-Request-ID": "req-123"})
    assert response.status_code == 404
    assert response.get_json() == {
        "type": "not_found",
        "title": "Not found",
        "status": 404,
        "detail": "Resource was not found",
        "request_id": "req-123",
    }


def test_production_requires_explicit_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        Settings.from_env()


def test_production_rejects_wildcard_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "production-secret-with-sufficient-entropy")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
        Settings.from_env()


def test_security_headers_and_trace_propagation(client, app) -> None:  # type: ignore[no-untyped-def]
    trace_id = uuid.uuid4().hex
    app.config["CORS_ALLOWED_ORIGINS"] = ("https://example.test",)
    response = client.get(
        "/health/live",
        headers={
            "Origin": "https://example.test",
            "X-Trace-ID": trace_id,
        },
    )
    assert response.status_code == 200
    assert response.headers["X-Trace-ID"] == trace_id
    assert response.headers["Access-Control-Allow-Origin"] == "https://example.test"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_disallowed_origin_is_rejected(client, app) -> None:  # type: ignore[no-untyped-def]
    app.config["CORS_ALLOWED_ORIGINS"] = ("https://allowed.test",)
    response = client.get("/health/live", headers={"Origin": "https://blocked.test"})
    assert response.status_code == 403
    assert response.get_json()["type"] == "origin_not_allowed"


def test_metrics_endpoint_uses_low_cardinality_endpoint_labels(client) -> None:  # type: ignore[no-untyped-def]
    client.get("/health/live")
    response = client.get("/internal/metrics")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert 'endpoint="health.live"' in text
    assert "http_requests_total" in text
    assert "http_server_errors_total" in text
    assert "http_request_duration_seconds_bucket" in text
    assert "celery_queue_depth" in text
    assert "db_pool_utilization_ratio" in text
    assert "elasticsearch_operation_duration_seconds" in text
    assert "payment_webhook_lag_seconds" in text
    assert "turn_credentials_issued_total" in text
    assert "webrtc_signaling_total" in text


def test_metrics_render_bounded_runtime_samples(client) -> None:  # type: ignore[no-untyped-def]
    increment_counter("webrtc_signaling_total", event="offer", outcome="failure")
    observe_histogram(
        "elasticsearch_operation_duration_seconds",
        0.125,
        operation="search",
        outcome="success",
    )
    response = client.get("/internal/metrics")
    text = response.get_data(as_text=True)
    assert 'webrtc_signaling_total{event="offer",outcome="failure"}' in text
    assert (
        'elasticsearch_operation_duration_seconds_count{operation="search",outcome="success"}'
        in text
    )


def test_financial_metrics_are_derived_from_deduplicated_database_state(client, app) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    with app.app_context():
        db.session.add(
            ProviderEvent(
                provider="sandbox",
                external_event_id="evt-observability-captured",
                event_type="payment.captured",
                payload_hash="0" * 64,
                processed_at=now,
            )
        )
        db.session.add(
            ReconciliationRun(
                provider="sandbox",
                status="MISMATCH",
                checked_count=3,
                discrepancy_count=2,
                details={"discrepancies": []},
                completed_at=now,
            )
        )
        db.session.commit()

    text = client.get("/internal/metrics").get_data(as_text=True)
    assert 'payment_events_total{outcome="captured",provider="sandbox"} 1' in text
    assert 'payment_reconciliation_runs_total{provider="sandbox",status="mismatch"} 1' in text
    assert 'payment_reconciliation_mismatches_total{provider="sandbox"} 2' in text


def test_json_formatter_includes_request_and_trace_context(app) -> None:  # type: ignore[no-untyped-def]
    formatter = JsonFormatter()
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "hello",
        (),
        None,
    )
    with app.test_request_context(
        "/",
        headers={
            "X-Request-ID": "req-logging",
            "X-Trace-ID": "a" * 32,
        },
    ):
        from flask import g

        g.request_id = "req-logging"
        g.trace_id = "a" * 32
        payload = json.loads(formatter.format(record))
    assert payload["message"] == "hello"
    assert payload["request_id"] == "req-logging"
    assert payload["trace_id"] == "a" * 32


def test_feature_flag_rollout_is_deterministic() -> None:
    subject = "user-123"
    rollouts = {"new_payment_flow": 50}
    first = is_feature_enabled(
        "new_payment_flow",
        subject_id=subject,
        rollouts=rollouts,
    )
    second = is_feature_enabled(
        "new_payment_flow",
        subject_id=subject,
        rollouts=rollouts,
    )
    assert first is second
    assert not is_feature_enabled(
        "new_payment_flow",
        rollouts={"new_payment_flow": 50},
    )
    assert is_feature_enabled(
        "new_payment_flow",
        subject_id=subject,
        rollouts={"new_payment_flow": 100},
    )
