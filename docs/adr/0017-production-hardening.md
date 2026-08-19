# ADR 0017: Production hardening and promotion

## Status

Accepted.

## Context

The marketplace now contains financial, realtime, dispute, WebRTC, and AI/risk capabilities. The production boundary therefore needs explicit security, observability, deployment, and CI rules rather than relying on framework defaults.

## Decision

### Request security

- Production rejects wildcard CORS configuration.
- Request bodies are bounded through Flask `MAX_CONTENT_LENGTH`.
- Redis-backed fixed-window rate limiting is enabled by default in production and remains opt-in in development/test.
- Standard security headers are added to API responses.
- Bearer-token authentication remains the current auth transport; CSRF middleware is not added until cookie-authenticated mutation endpoints exist.
- Health and internal metrics endpoints are exempt from rate limiting to avoid turning a Redis incident into a restart/monitoring storm.

### Observability

- Every request has a `request_id` and 32-hex `trace_id`; valid W3C `traceparent` trace IDs are propagated.
- JSON logs include request/trace context and only explicitly safe identifiers.
- HTTP metrics use endpoint names rather than raw URL paths to avoid unbounded cardinality.
- Metrics are exposed at `/internal/metrics`; production ingress must not expose this path publicly.
- Existing audit events continue carrying `request_id`; audit storage remains immutable through the existing domain controls.

This PR establishes correlation and HTTP metrics. Full OpenTelemetry spans across DB, Celery, and external payment providers remain a follow-up because those adapters need explicit instrumentation boundaries rather than monkey-patching them in shared middleware.

### Feature flags

The following risky rollouts are recognized centrally:

- `new_payment_flow`
- `new_matching_model`
- `new_commission_formula`
- `new_search_ranking`
- `new_dispute_engine`

Rollouts are deterministic per subject and configured as integer percentages from 0 to 100. Unknown flags fail closed with an exception. Business domains must opt into a flag explicitly; this hardening PR does not change existing business behavior merely by defining flags.

### Kubernetes

- The namespace enforces the restricted Pod Security profile.
- API and workers use separate ServiceAccounts and disable token automount.
- Containers run non-root with a read-only root filesystem, RuntimeDefault seccomp, no privilege escalation, and all Linux capabilities dropped.
- Requests/limits and API liveness/readiness/startup probes are mandatory.
- Secrets are referenced from a cluster Secret and never committed into manifests.
- NetworkPolicy defaults to deny; external provider/object-storage/TURN egress must be added through an environment-specific controlled egress policy rather than opening general internet access in the base.

The repository validator checks these invariants whenever Kubernetes files change.

### CI and release

- PRs keep one aggregate required `PR Gate / gate` check.
- Kubernetes validation and dependency auditing are impact-selected.
- Slow E2E, complete security/dependency work, migration downgrade/upgrade cycles, and backup restore are nightly/pre-release responsibilities rather than default PR work.
- `main` runs full core tests, builds and pushes a SHA-addressed image, scans the pushed digest, emits an SBOM, and can deploy that same digest to staging when environment configuration is enabled.
- Production release accepts an already-built digest from a successful main run and never rebuilds the image.

Browser E2E, external payment sandbox, cross-browser WebRTC/TURN matrix, long load/concurrency soak, and full DAST are not fabricated in this backend-only repository. They remain nightly/pre-release requirements once the corresponding browser harness, external sandbox credentials, TURN environment, and load/DAST targets exist.

### Repository administration

`main` branch protection must be configured in GitHub repository settings with direct pushes disabled, PR required, `PR Gate / gate` required, resolved conversations required, and stale approvals dismissed. This is repository administration state, not application code; it is documented here rather than silently mutated by a feature PR.

## Consequences

- Shared runtime changes correctly select broader core validation because they affect every request.
- Kubernetes-only edits remain cheap to validate.
- A Redis outage can make rate-limited business endpoints unavailable, but it does not affect liveness or internal metrics; readiness already reports Redis health.
- In-memory HTTP counters are process-local. Production aggregation must scrape every API replica and aggregate in the monitoring backend.
- Exact image-digest promotion makes staging/production provenance auditable and rollbackable without rebuilding.
