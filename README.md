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
- Project close and reviews are contract-backed: the contract must be active, and current-version milestones must be approved before close.
- Financial milestone transitions are intentionally reserved for the Money phase: funding, release, ledger, commission, refund, and payout authority are not implemented here.

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

Integration tests require the corresponding real service. PR CI starts PostgreSQL, Redis, or Elasticsearch only when the impact detector selects that dependency. Contract and milestone changes select the focused PostgreSQL contract integration test in addition to any other affected database smoke tests.

## Architecture rules

PostgreSQL is the source of truth. Redis is ephemeral. Elasticsearch is a rebuildable search projection and must not become authoritative business state.

HTTP controllers stay thin: controller → application/domain service → repository/external adapter. Business-state transitions and authorization decisions belong below the route layer.

Marketplace money values are stored as integer minor units plus a three-letter currency code. Proposal versions and contract versions are immutable historical records. Search updates are written to the PostgreSQL outbox in the same transaction as the source change and indexed asynchronously.

See `docs/adr/` for recorded architectural decisions. `docs/openapi.yaml` is the Marketplace Core API contract, and `docs/openapi/contracts.yaml` documents the Contract-phase endpoints added after it.
