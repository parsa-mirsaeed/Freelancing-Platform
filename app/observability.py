from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime

from flask import Blueprint, Flask, Response, g, has_request_context, request

metrics_bp = Blueprint("metrics", __name__)

_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
_lock = threading.Lock()
_request_totals: Counter[tuple[str, str, int]] = Counter()
_duration_counts: defaultdict[tuple[str, str], list[int]] = defaultdict(
    lambda: [0] * (len(_BUCKETS) + 1)
)
_duration_sums: defaultdict[tuple[str, str], float] = defaultdict(float)


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

    @app.before_request
    def start_observation() -> None:
        g.request_started_at = time.perf_counter()

    @app.after_request
    def observe_request(response: Response) -> Response:
        started = getattr(g, "request_started_at", None)
        if started is not None and request.endpoint != "metrics.metrics":
            duration = max(0.0, time.perf_counter() - started)
            endpoint = request.endpoint or "unmatched"
            _observe(request.method, endpoint, response.status_code, duration)
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


def _observe(method: str, endpoint: str, status: int, duration: float) -> None:
    key = (method, endpoint)
    with _lock:
        _request_totals[(method, endpoint, status)] += 1
        _duration_sums[key] += duration
        counts = _duration_counts[key]
        for index, boundary in enumerate(_BUCKETS):
            if duration <= boundary:
                counts[index] += 1
        counts[-1] += 1


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
                "# HELP http_request_duration_seconds HTTP request duration.",
                "# TYPE http_request_duration_seconds histogram",
            ]
        )
        for (method, endpoint), counts in sorted(_duration_counts.items()):
            for index, boundary in enumerate(_BUCKETS):
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
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


def _labels(**values: str) -> str:
    cleaned = {key: value.replace('"', "") for key, value in values.items()}
    return ",".join(f'{key}="{value}"' for key, value in sorted(cleaned.items()))
