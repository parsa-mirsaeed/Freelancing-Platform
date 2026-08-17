# Freelancing Platform

A skill-sharing and freelancing marketplace built as a domain-driven modular Flask monolith.

## Implemented

### Foundation

- Flask application factory and domain-oriented packages.
- PostgreSQL persistence through SQLAlchemy 2 and Alembic.
- Redis extension and Celery application factory.
- Identity foundation with Argon2 password hashing, access tokens, rotating database-backed refresh sessions, and freelancer/employer self-registration.
- RBAC helpers plus resource-ownership policy seams.
- Immutable audit events and dependency-aware health endpoints.
- OpenAPI 3.1, non-root containerization, and impact-based PR CI.

### Marketplace Core

- Freelancer profiles, canonical skills, languages, rates in integer minor units, and availability rules/exceptions.
- Portfolio items with file metadata reserved for the later safe-upload pipeline.
- Gigs with Basic/Standard/Premium packages, delivery days, revisions, requirements, and integer minor-unit prices.
- Employer projects with skills and integer minor-unit budget ranges.
- Versioned proposals and enforced negotiation transitions; prior commercial terms are never overwritten.
- PostgreSQL transactional outbox events for freelancer search refreshes.
- Elasticsearch 9.x freelancer projection with monotonic projection versions and lexical/filter search.

### Contract

- Proposal acceptance atomically creates one contract backed by an immutable snapshot of the accepted proposal's current version and project scope.
- Contract Version 1 stores a canonical SHA-256 document hash, two required parties, and milestone commercial values copied from the signed snapshot.
- Employer and freelancer signatures are hash-bound and idempotency-key protected; the contract activates only after both required signatures exist.
- Contract versions, signatures, and milestone progress events are append-only at the ORM layer and protected against direct mutation by PostgreSQL triggers.
- Milestone execution progress supports freelancer start/submit/resubmit and employer request-changes/approve transitions with resource-level authorization and idempotent repeated transitions.

### Money

- Payment providers are behind a provider-neutral interface; the included sandbox adapter is deterministic and network-free for local development and CI.
- Milestone funding is captured from signed, deduplicated provider webhooks and posts to an internal double-entry ledger.
- Every committed journal is single-currency and balanced; PostgreSQL deferrable constraint triggers reject unbalanced journals.
- Journal transactions and ledger entries are append-only in both the ORM and PostgreSQL. Corrections use reversal journals.
- Escrow is derived from ledger entries. Full funding moves milestones to `FUNDED`; work cannot start until the contracted amount is present.
- Employer release requires an approved milestone, locks financial state, posts freelancer wallet and platform commission credits, and moves the milestone to `RELEASED`.
- Full pre-work refunds reverse escrow entitlement through the ledger and reset the milestone to `CREATED` only after provider success.
- Wallet views are derived from ledger entries rather than a mutable user balance.
- Payouts reserve wallet funds in a locked database transaction before the provider call and reverse the reservation on provider failure.
- Financial mutations use scoped idempotency keys; provider events use provider/event-id deduplication and signature verification.
- Reconciliation compares captured provider transactions against local payment and funding records and emits mismatch outbox events.
- Project close now requires all current-version milestones to be financially released.

## Local development

Create a virtual environment and install development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Start the local data/search services:

```bash
docker compose -f infra/docker/compose.yml up -d postgres redis elasticsearch
```

Apply the schema:

```bash
export DATABASE_URL='postgresql+psycopg://freelancing:freelancing@localhost:5432/freelancing'
export REDIS_URL='redis://localhost:6379/0'
export ELASTICSEARCH_URL='http://localhost:9200'
export ELASTICSEARCH_INDEX_PREFIX='freelancing-development'
export SECRET_KEY='replace-this-local-secret'
alembic upgrade head
```

The default local Money adapter is `sandbox`. Override these only when needed:

```bash
export PAYMENT_WEBHOOK_SECRET='replace-this-local-webhook-secret'
export PLATFORM_COMMISSION_BPS='1000'
```

Run the API:

```bash
flask --app 'app:create_app()' run --debug
```

Run the worker and periodic outbox drain in separate processes:

```bash
celery -A app.celery_worker.celery_app worker -l info
celery -A app.celery_worker.celery_app beat -l info
```

Or start the complete local stack:

```bash
docker compose -f infra/docker/compose.yml up --build
```

## Validation

Fast local checks:

```bash
ruff check app ci tests
ruff format --check app ci tests
mypy app ci
pytest -m unit tests/unit
```

Integration tests require the corresponding real service. PR CI starts PostgreSQL, Redis, or Elasticsearch only when the impact detector selects that dependency. Payment, ledger, payout, milestone, or relevant project changes select the focused PostgreSQL Money invariant suite. Redis remains skipped for Money-only work, while Elasticsearch is selected only when a changed domain affects its projection.

## Architecture rules

PostgreSQL is the source of truth. Redis is ephemeral. Elasticsearch is a rebuildable search projection and must not become authoritative business state.

HTTP controllers stay thin: controller → application/domain service → repository/external adapter. Business-state transitions and authorization decisions belong below the route layer.

Marketplace money values are stored as integer minor units plus a three-letter currency code. Proposal versions and contract versions are immutable historical records. Financial balances are derived from immutable double-entry ledger entries, and external provider state never replaces the internal ledger as the accounting authority. Search updates are written to the PostgreSQL outbox in the same transaction as the source change and indexed asynchronously.

See `docs/adr/` for recorded architectural decisions. `docs/openapi.yaml` is the Marketplace Core API contract, while phase-owned fragments under `docs/openapi/` document Contract and Money endpoints.
