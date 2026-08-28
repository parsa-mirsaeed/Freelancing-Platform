from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from weakref import WeakSet

from flask import (
    Blueprint,
    Flask,
    Response,
    current_app,
    g,
    has_app_context,
    has_request_context,
    request,
)
from redis.exceptions import RedisError
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, redis_extension

metrics_bp = Blueprint("metrics", __name__)

_HTTP_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
_DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_MESSAGE_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
_WEBHOOK_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0, 60.0, 300.0)
_SLOW_QUERY_SECONDS = 0.5
_CELERY_QUEUES = (
    "default",
    "payments",
    "reconciliation",
    "notifications",
    "search_index",
    "files",
)

_lock = threading.Lock()
_request_totals: Counter[tuple[str, str, int]] = Counter()
_server_error_totals: Counter[tuple[str, str]] = Counter()
_duration_counts: defaultdict[tuple[str, str], list[int]] = defaultdict(
    lambda: [0] * (len(_HTTP_BUCKETS) + 1)
)
_duration_sums: defaultdict[tuple[str, str], float] = defaultdict(float)
_counter_values: defaultdict[str, Counter[tuple[tuple[str, str], ...]]] = defaultdict(Counter)
_gauge_values: defaultdict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
_histogram_counts: defaultdict[
    tuple[str, tuple[tuple[str, str], ...]], list[int]
] = defaultdict(list)
_histogram_sums: defaultdict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_observed_engines: WeakSet[Engine] = WeakSet()
_engine_lock = threading.Lock()


@dataclass(frozen=True, slots=True)
class MetricSpec:
    kind: str
    help: str
    labels: tuple[str, ...] = ()
    buckets: tuple[float, ...] = _DEFAULT_BUCKETS


_METRICS = {
    "socket_active_connections": MetricSpec(
        "gauge",
        "Authenticated Socket.IO principals currently present in Redis.",
    ),
    "message_delivery_duration_seconds": MetricSpec(
        "histogram",
        "Time from message creation to first recorded delivery receipt.",
        buckets=_MESSAGE_BUCKETS,
    ),
    "celery_task_failures_total": MetricSpec(
        "counter",
        "Celery task executions that ended in failure.",
        ("task",),
    ),
    "celery_task_retries_total": MetricSpec(
        "counter",
        "Celery task retry attempts.",
        ("task",),
    ),
    "celery_queue_depth": MetricSpec(
        "gauge",
        "Current Redis-backed Celery queue depth.",
        ("queue",),
    ),
    "payment_events_total": MetricSpec(
        "counter",
        "Unique payment provider events committed by outcome.",
        ("provider", "outcome"),
    ),
    "payment_webhook_lag_seconds": MetricSpec(
        "histogram",
        "Lag from provider event creation to verified webhook processing.",
        ("provider", "event_type"),
        _WEBHOOK_BUCKETS,
    ),
    "payment_reconciliation_runs_total": MetricSpec(
        "counter",
        "Payment reconciliation runs by terminal status.",
        ("provider", "status"),
    ),
    "payment_reconciliation_mismatches_total": MetricSpec(
        "counter",
        "Individual payment reconciliation mismatches.",
        ("provider",),
    ),
    "db_pool_checked_out": MetricSpec(
        "gauge",
        "Database connections currently checked out from this process pool.",
    ),
    "db_pool_size": MetricSpec(
        "gauge",
        "Configured base database pool size for this process.",
    ),
    "db_pool_overflow": MetricSpec(
        "gauge",
        "Current database pool overflow connections for this process.",
    ),
    "db_pool_utilization_ratio": MetricSpec(
        "gauge",
        "Checked-out database connections divided by base pool size.",
    ),
    "db_query_duration_seconds": MetricSpec(
        "histogram",
        "Database query execution duration by SQL operation.",
        ("operation",),
    ),
    "db_slow_queries_total": MetricSpec(
        "counter",
        f"Database queries taking at least {_SLOW_QUERY_SECONDS:.1f} seconds.",
        ("operation",),
    ),
    "elasticsearch_operation_duration_seconds": MetricSpec(
        "histogram",
        "Elasticsearch operation duration by operation and outcome.",
        ("operation", "outcome"),
    ),
    "turn_credentials_issued_total": MetricSpec(
        "counter",
        "TURN REST credentials issued to authenticated sessions.",
    ),
    "webrtc_signaling_total": MetricSpec(
        "counter",
        "WebRTC signaling requests by event and server-visible outcome.",
        ("event", "outcome"),
    ),
}

_SHARED_COUNTERS = {
    "celery_task_failures_total",
    "celery_task_retries_total",
}


def _request_context() -> dict[str, object]:
    if not has_request_context():
        return {}
    result: dict[str, object] = {
        "request_id": getattr(g, "request_id", None),
        "trace_id": getattr(g, "trace_id", None),
    }
    current_user = getattr(g, "current_user", None)
    if current_user is not None:
        result["user_id"] = str(current_user.id)
    return {key: value for key, value in result.items() if value is not None}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(_request_context())
        for field in (
            "contract_id",
            "payment_id",
            "provider_event_id",
            "celery_task_id",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def configure_observability(app: Flask) -> None:
    if app.config.get("LOG_JSON", True):
        root = logging.getLogger()
        if not root.handlers:
            root.addHandler(logging.StreamHandler())
        formatter = JsonFormatter()
        for handler in root.handlers:
            handler.setFormatter(formatter)

    _configure_database_metrics(app)

    @app.before_request
    def start_observation() -> None:
        g.request_started_at = time.perf_counter()

    @app.after_request
    def observe_request(response: Response) -> Response:
        started = getattr(g, "request_started_at", None)
        if started is not None and request.endpoint != "metrics.metrics":
            duration = max(0.0, time.perf_counter() - started)
            endpoint = request.endpoint or "unmatched"
            _observe_request(request.method, endpoint, response.status_code, duration)
        return response


def assign_trace_id() -> str:
    supplied = request.headers.get("X-Trace-ID", "").strip().lower()
    if len(supplied) == 32 and all(character in "0123456789abcdef" for character in supplied):
        return supplied
    traceparent = request.headers.get("traceparent", "").strip().lower()
    parts = traceparent.split("-")
    if len(parts) == 4:
        trace_id = parts[1]
        if (
            len(trace_id) == 32
            and trace_id != "0" * 32
            and all(character in "0123456789abcdef" for character in trace_id)
        ):
            return trace_id
    return uuid.uuid4().hex


def increment_counter(name: str, amount: int = 1, **labels: str) -> None:
    if amount < 0:
        raise ValueError("Counter increments must be non-negative")
    key = _metric_key(name, "counter", labels)
    with _lock:
        _counter_values[name][key] += amount


def increment_shared_counter(name: str, amount: int = 1, **labels: str) -> None:
    if name not in _SHARED_COUNTERS:
        raise ValueError(f"{name} is not configured as a shared counter")
    if amount < 0:
        raise ValueError("Counter increments must be non-negative")
    key = _metric_key(name, "counter", labels)
    if _write_shared_counter(name, key, amount):
        return
    with _lock:
        _counter_values[name][key] += amount


def observe_histogram(name: str, value: float, **labels: str) -> None:
    if value < 0:
        value = 0.0
    key = _metric_key(name, "histogram", labels)
    spec = _METRICS[name]
    storage_key = (name, key)
    with _lock:
        counts = _histogram_counts[storage_key]
        if not counts:
            counts.extend([0] * (len(spec.buckets) + 1))
        for index, boundary in enumerate(spec.buckets):
            if value <= boundary:
                counts[index] += 1
        counts[-1] += 1
        _histogram_sums[storage_key] += value


def _metric_key(
    name: str,
    expected_kind: str,
    labels: dict[str, str],
) -> tuple[tuple[str, str], ...]:
    spec = _METRICS.get(name)
    if spec is None:
        raise ValueError(f"Unknown metric: {name}")
    if spec.kind != expected_kind:
        raise ValueError(f"{name} is a {spec.kind}, not a {expected_kind}")
    if set(labels) != set(spec.labels):
        expected = ", ".join(spec.labels) or "(none)"
        raise ValueError(f"{name} labels must be exactly: {expected}")
    return tuple((label, _clean_label(str(labels[label]))) for label in spec.labels)


def _observe_request(method: str, endpoint: str, status: int, duration: float) -> None:
    key = (method, endpoint)
    with _lock:
        _request_totals[(method, endpoint, status)] += 1
        if status >= 500:
            _server_error_totals[key] += 1
        _duration_sums[key] += duration
        counts = _duration_counts[key]
        for index, boundary in enumerate(_HTTP_BUCKETS):
            if duration <= boundary:
                counts[index] += 1
        counts[-1] += 1


def _configure_database_metrics(app: Flask) -> None:
    with app.app_context():
        engine = db.engine
    with _engine_lock:
        if engine in _observed_engines:
            return
        event.listen(engine, "before_cursor_execute", _before_cursor_execute)
        event.listen(engine, "after_cursor_execute", _after_cursor_execute)
        _observed_engines.add(engine)


def _before_cursor_execute(
    _connection: Any,
    _cursor: Any,
    _statement: str,
    _parameters: Any,
    context: Any,
    _executemany: bool,
) -> None:
    context._freelancing_query_started_at = time.perf_counter()


def _after_cursor_execute(
    _connection: Any,
    _cursor: Any,
    statement: str,
    _parameters: Any,
    context: Any,
    _executemany: bool,
) -> None:
    started = getattr(context, "_freelancing_query_started_at", None)
    if not isinstance(started, float):
        return
    duration = max(0.0, time.perf_counter() - started)
    operation = _sql_operation(statement)
    observe_histogram("db_query_duration_seconds", duration, operation=operation)
    if duration >= _SLOW_QUERY_SECONDS:
        increment_counter("db_slow_queries_total", operation=operation)


def _sql_operation(statement: str) -> str:
    candidate = statement.lstrip().split(None, 1)
    if not candidate:
        return "OTHER"
    operation = candidate[0].upper()
    if operation in {"SELECT", "INSERT", "UPDATE", "DELETE", "WITH", "CREATE", "ALTER", "DROP"}:
        return operation
    return "OTHER"


@metrics_bp.get("/internal/metrics")
def metrics() -> Response:
    lines = [
        "# HELP http_requests_total HTTP requests completed.",
        "# TYPE http_requests_total counter",
    ]
    with _lock:
        for (method, endpoint, status), count in sorted(_request_totals.items()):
            labels = _labels(method=method, endpoint=endpoint, status=str(status))
            lines.append(f"http_requests_total{{{labels}}} {count}")
        lines.extend(
            [
                "# HELP http_server_errors_total HTTP 5xx responses completed.",
                "# TYPE http_server_errors_total counter",
            ]
        )
        for (method, endpoint), count in sorted(_server_error_totals.items()):
            labels = _labels(method=method, endpoint=endpoint)
            lines.append(f"http_server_errors_total{{{labels}}} {count}")
        lines.extend(
            [
                "# HELP http_request_duration_seconds HTTP request duration.",
                "# TYPE http_request_duration_seconds histogram",
            ]
        )
        for (method, endpoint), counts in sorted(_duration_counts.items()):
            for index, boundary in enumerate(_HTTP_BUCKETS):
                labels = _labels(method=method, endpoint=endpoint, le=str(boundary))
                lines.append(f"http_request_duration_seconds_bucket{{{labels}}} {counts[index]}")
            inf_labels = _labels(method=method, endpoint=endpoint, le="+Inf")
            lines.append(f"http_request_duration_seconds_bucket{{{inf_labels}}} {counts[-1]}")
            count_labels = _labels(method=method, endpoint=endpoint)
            lines.append(f"http_request_duration_seconds_count{{{count_labels}}} {counts[-1]}")
            lines.append(
                "http_request_duration_seconds_sum"
                f"{{{count_labels}}} {_duration_sums[(method, endpoint)]:.9f}"
            )

    dynamic_counters = _dynamic_counters()
    dynamic_gauges = _dynamic_gauges()
    shared_counters = _read_shared_counters()
    with _lock:
        local_counters = {name: Counter(values) for name, values in _counter_values.items()}
        local_gauges = {name: dict(values) for name, values in _gauge_values.items()}
        local_histograms = {key: list(values) for key, values in _histogram_counts.items()}
        local_histogram_sums = dict(_histogram_sums)

    for source in (shared_counters, dynamic_counters):
        for name, values in source.items():
            local_counters.setdefault(name, Counter()).update(values)
    for name, values in dynamic_gauges.items():
        local_gauges.setdefault(name, {}).update(values)

    for name, spec in _METRICS.items():
        lines.extend([f"# HELP {name} {spec.help}", f"# TYPE {name} {spec.kind}"])
        if spec.kind == "counter":
            for labels, value in sorted(local_counters.get(name, {}).items()):
                lines.append(_sample(name, labels, value))
        elif spec.kind == "gauge":
            for labels, value in sorted(local_gauges.get(name, {}).items()):
                lines.append(_sample(name, labels, value))
        else:
            for (metric_name, labels), counts in sorted(local_histograms.items()):
                if metric_name != name:
                    continue
                for index, boundary in enumerate(spec.buckets):
                    bucket_labels = (*labels, ("le", str(boundary)))
                    lines.append(_sample(f"{name}_bucket", bucket_labels, counts[index]))
                lines.append(_sample(f"{name}_bucket", (*labels, ("le", "+Inf")), counts[-1]))
                lines.append(_sample(f"{name}_count", labels, counts[-1]))
                lines.append(_sample(f"{name}_sum", labels, local_histogram_sums[(name, labels)]))

    return Response("\n".join(lines) + "\n", mimetype="text/plain")


def _dynamic_counters() -> dict[str, Counter[tuple[tuple[str, str], ...]]]:
    result: dict[str, Counter[tuple[tuple[str, str], ...]]] = {}
    if not has_app_context():
        return result
    from app.payments.models import ProviderEvent, ReconciliationRun

    try:
        payment_samples: Counter[tuple[tuple[str, str], ...]] = Counter()
        rows = db.session.execute(
            select(ProviderEvent.provider, ProviderEvent.event_type, func.count(ProviderEvent.id))
            .where(ProviderEvent.processed_at.is_not(None))
            .group_by(ProviderEvent.provider, ProviderEvent.event_type)
        )
        for provider, event_type, count in rows:
            outcome = (
                "captured"
                if event_type == "payment.captured"
                else "failed"
                if event_type == "payment.failed"
                else "ignored"
            )
            payment_samples[(("provider", str(provider)), ("outcome", outcome))] += int(count)
        result["payment_events_total"] = payment_samples

        run_samples: Counter[tuple[tuple[str, str], ...]] = Counter()
        rows = db.session.execute(
            select(
                ReconciliationRun.provider,
                ReconciliationRun.status,
                func.count(ReconciliationRun.id),
            )
            .where(ReconciliationRun.status != "RUNNING")
            .group_by(ReconciliationRun.provider, ReconciliationRun.status)
        )
        for provider, status, count in rows:
            run_samples[(("provider", str(provider)), ("status", str(status).lower()))] = int(count)
        result["payment_reconciliation_runs_total"] = run_samples

        mismatch_samples: Counter[tuple[tuple[str, str], ...]] = Counter()
        rows = db.session.execute(
            select(ReconciliationRun.provider, func.sum(ReconciliationRun.discrepancy_count))
            .where(ReconciliationRun.status != "RUNNING")
            .group_by(ReconciliationRun.provider)
        )
        for provider, count in rows:
            mismatch_samples[(("provider", str(provider)),)] = int(count or 0)
        result["payment_reconciliation_mismatches_total"] = mismatch_samples
    except SQLAlchemyError:
        db.session.rollback()
        return {}
    return result


def _dynamic_gauges() -> dict[str, dict[tuple[tuple[str, str], ...], float]]:
    result: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
    if not has_app_context():
        return result
    try:
        pool = db.engine.pool
        checkedout_fn = getattr(pool, "checkedout", None)
        size_fn = getattr(pool, "size", None)
        overflow_fn = getattr(pool, "overflow", None)
        if callable(checkedout_fn) and callable(size_fn):
            checked_out = float(checkedout_fn())
            size = float(size_fn())
            result["db_pool_checked_out"][()] = checked_out
            result["db_pool_size"][()] = size
            result["db_pool_utilization_ratio"][()] = checked_out / size if size > 0 else 0.0
        if callable(overflow_fn):
            result["db_pool_overflow"][()] = float(overflow_fn())
    except (AttributeError, TypeError, ValueError):
        pass

    try:
        client = redis_extension.get_client(current_app)
        for queue in _CELERY_QUEUES:
            key = (("queue", queue),)
            result["celery_queue_depth"][key] = float(client.llen(queue))
        result["socket_active_connections"][()] = float(
            sum(1 for _ in client.scan_iter(match="socket-principal:*", count=500))
        )
    except (RedisError, OSError):
        pass
    return result


def _write_shared_counter(
    name: str,
    labels: tuple[tuple[str, str], ...],
    amount: int,
) -> bool:
    if not has_app_context():
        return False
    try:
        client = redis_extension.get_client(current_app)
        client.hincrby(_shared_counter_key(name), _encode_labels(labels), amount)
        return True
    except (RedisError, OSError):
        return False


def _read_shared_counters() -> dict[str, Counter[tuple[tuple[str, str], ...]]]:
    result: dict[str, Counter[tuple[tuple[str, str], ...]]] = {}
    if not has_app_context():
        return result
    try:
        client = redis_extension.get_client(current_app)
        for name in sorted(_SHARED_COUNTERS):
            samples: Counter[tuple[tuple[str, str], ...]] = Counter()
            for raw_labels, raw_value in client.hgetall(_shared_counter_key(name)).items():
                labels = _decode_labels(str(raw_labels))
                if labels is None:
                    continue
                try:
                    samples[labels] = int(raw_value)
                except (TypeError, ValueError):
                    continue
            result[name] = samples
    except (RedisError, OSError):
        return {}
    return result


def _shared_counter_key(name: str) -> str:
    return f"observability:counter:{name}"


def _encode_labels(labels: tuple[tuple[str, str], ...]) -> str:
    return json.dumps(dict(labels), sort_keys=True, separators=(",", ":"))


def _decode_labels(value: str) -> tuple[tuple[str, str], ...] | None:
    try:
        document = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(document, dict):
        return None
    return tuple(sorted((str(key), _clean_label(str(item))) for key, item in document.items()))


def _sample(
    name: str,
    labels: tuple[tuple[str, str], ...],
    value: float | int,
) -> str:
    if not labels:
        return f"{name} {value}"
    return f"{name}{{{_labels(**dict(labels))}}} {value}"


def _labels(**values: str) -> str:
    return ",".join(
        f'{key}="{_clean_label(value)}"' for key, value in sorted(values.items())
    )


def _clean_label(value: str) -> str:
    return value.replace("\\", "").replace('"', "").replace("\n", " ")[:120]
