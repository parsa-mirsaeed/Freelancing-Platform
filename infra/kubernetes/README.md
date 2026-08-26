# Kubernetes deployment contract

The manifests are intentionally environment-neutral and do not contain secret values.

Production deployment must provide `freelancing-runtime-secrets` from the cluster secret manager with at least:

- `secret-key`
- `database-url`
- `redis-url`
- `s3-access-key`
- `s3-secret-key`

Payment-enabled production workloads additionally require provider credentials. For Stripe, provision:

- `stripe-secret-key`
- `stripe-publishable-key`
- `stripe-webhook-secret`

Do not mount Stripe credentials into workers that do not execute payment-provider calls. Generic production workloads keep `PAYMENT_RUNTIME_ENABLED=false`; environment overlays enable it only for the API/payment worker that has the corresponding secrets and managed provider egress.

Image references in the manifests are bootstrap placeholders. Staging and production automation replace every runtime image with the immutable digest produced by the `main` workflow; production reuses that exact digest rather than rebuilding.

Runtime isolation follows the blueprint and the queues that actually exist today:

- `freelancing-api`: REST/API traffic.
- `freelancing-socket`: long-lived Socket.IO/WebRTC signaling traffic, one Gunicorn process per pod and Redis as the cross-pod message queue.
- `freelancing-worker`: default Celery queue only.
- `celery-payments`: payment queue only.
- `celery-notifications`: notification queue only.
- `celery-search`: `search_index` queue only.
- `celery-files`: file-processing queue only.

There is intentionally no `celery-ml` deployment yet because the current AI baseline has no asynchronous ML task route. Add it when an actual ML queue exists rather than deploying an idle placeholder.

The namespace enforces the Kubernetes restricted Pod Security profile. API, Socket.IO, and worker pods use separated workload identities, disable service-account token automount, run as UID/GID 10001, use a read-only root filesystem, drop all Linux capabilities, and write temporary files only to an `emptyDir` mounted at `/tmp`.

API and Socket.IO probes deliberately separate concerns:

- `/health/live` is process-only and must not depend on PostgreSQL, Redis, Elasticsearch, object storage, or payment providers.
- `/health/ready` decides whether the pod should receive traffic.
- `/health/startup` gives dependencies time to become ready without causing a liveness restart loop.

`default-deny` blocks traffic by default. The included API/socket/worker policies allow DNS and required in-cluster data-plane ports only. Environments using external object storage, TURN, notification, or payment providers must route those destinations through an explicitly managed egress policy/gateway; do not replace default-deny with unrestricted internet egress. Stripe activation therefore requires managed HTTPS egress to Stripe from payment-enabled workloads; use an environment-specific egress gateway/proxy or FQDN-aware policy rather than granting internet access to every worker.

Ingress configuration is environment-owned. Route normal HTTP traffic to `freelancing-api` and Socket.IO/WebSocket paths to `freelancing-socket`; configure connection affinity appropriate for the ingress implementation while Redis preserves cross-instance fan-out.

Validate manifests locally with:

```bash
python -m pip install PyYAML
python ci/validate_k8s.py
```
