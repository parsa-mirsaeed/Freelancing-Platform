# Production observability

The application exposes Prometheus text metrics at `/internal/metrics`. Keep this endpoint on the internal scrape path; it is operational telemetry rather than a public product API.

The metric design intentionally uses bounded labels. User IDs, contract IDs, payment references, provider event IDs, request IDs and trace IDs belong in structured logs and traces, not Prometheus labels.

## HTTP

`http_request_duration_seconds` is the API latency histogram. Calculate p50, p95 and p99 with `histogram_quantile`, for example:

```promql
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))
```

`http_server_errors_total` counts HTTP 5xx responses. A five-minute 5xx rate can be calculated as:

```promql
sum(rate(http_server_errors_total[5m]))
/
sum(rate(http_requests_total[5m]))
```

Endpoint labels use Flask endpoint names instead of raw URLs, so UUIDs and other path parameters do not create unbounded series.

## Socket.IO and messaging

`socket_active_connections` counts authenticated socket-principal keys currently present in Redis. The keys already expire with the authenticated socket principal, so stale process-local counters do not survive worker crashes. Because each API/socket replica reads the same Redis aggregate, dashboards should not sum this gauge across identical replicas.

`message_delivery_duration_seconds` measures the time from persisted message creation to the first newly persisted `DELIVERED` receipt. The observation is emitted only after the receipt transaction commits.

## Celery

`celery_queue_depth{queue=...}` reads the bounded application queues directly from the Redis broker:

- `default`
- `payments`
- `reconciliation`
- `notifications`
- `search_index`
- `files`

`celery_task_failures_total{task=...}` and `celery_task_retries_total{task=...}` are Redis-backed counters so worker-process restarts do not reset them. Task labels are Celery task names, not task IDs.

## Payments

`payment_events_total{provider,outcome}` is derived from processed `ProviderEvent` rows. Provider events are already unique on `(provider, external_event_id)`, so duplicate webhook delivery does not inflate payment outcome counts. Outcomes are bounded to `captured`, `failed`, and `ignored`.

A payment success ratio can be calculated without ignored events:

```promql
sum(rate(payment_events_total{outcome="captured"}[15m]))
/
(
  sum(rate(payment_events_total{outcome="captured"}[15m]))
  +
  sum(rate(payment_events_total{outcome="failed"}[15m]))
)
```

`payment_webhook_lag_seconds{provider,event_type}` uses the Stripe event `created` timestamp only after signature verification succeeds. The event-type label is restricted to the supported Checkout event types plus `other`. Duplicate deliveries can contribute additional webhook-lag observations, which is intentional because lag measures provider delivery behavior rather than business-side deduplication.

`payment_reconciliation_runs_total{provider,status}` and `payment_reconciliation_mismatches_total{provider}` are derived from authoritative `ReconciliationRun` rows instead of worker memory. This keeps the metrics correct across retries and multiple reconciliation workers.

## Database

`db_pool_checked_out`, `db_pool_size`, `db_pool_overflow`, and `db_pool_utilization_ratio` expose SQLAlchemy pool pressure when the configured pool provides those counters.

`db_query_duration_seconds{operation}` records SQL execution time with the operation restricted to a small fixed set. `db_slow_queries_total{operation}` counts queries taking at least 0.5 seconds. SQL text, table values, user identifiers and request parameters are never labels.

## Elasticsearch

`elasticsearch_operation_duration_seconds{operation,outcome}` measures `ensure_index`, `index`, and `search` operations, with outcome bounded to `success` or `failure`.

## TURN and WebRTC

`turn_credentials_issued_total` measures application-visible TURN usage: issuance of ephemeral TURN REST credentials. Relay allocations, bytes and transport-level failures occur inside coturn and should be collected from coturn-native operational telemetry when that infrastructure exporter is deployed.

`webrtc_signaling_total{event,outcome}` covers server-visible offer, answer and ICE-candidate signaling. A signaling failure ratio is:

```promql
sum(rate(webrtc_signaling_total{outcome="failure"}[5m]))
/
sum(rate(webrtc_signaling_total[5m]))
```

Browser-only ICE/media failures that never reach the signaling server require client/coturn telemetry and are deliberately not inferred by the backend.

## Logs and tracing

JSON logs continue to carry request and trace correlation plus safe identity/resource context (`request_id`, `trace_id`, `user_id` where safe, and explicit `contract_id`, `payment_id`, `provider_event_id`, or `celery_task_id` log extras).

The current implementation provides trace-ID correlation across HTTP work and structured resource context. A full OpenTelemetry-style distributed trace spanning API, database, Celery and payment-provider calls is a valuable future extension, but this metrics PR does not pretend correlation IDs are equivalent to a complete distributed tracing backend.

## Alerting guidance

Alert on sustained behavior, not single samples. Useful starting signals are rising 5xx rate, p95/p99 API latency, growing Celery queue depth, repeated task retries/failures, non-zero reconciliation mismatches, abnormal webhook lag, database pool saturation, slow-query growth, Elasticsearch failure latency, and elevated WebRTC signaling failure rate. Thresholds must be calibrated from staging/load-test baselines before production paging is enabled.
