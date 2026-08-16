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
- Reviews gated by a closed employer-owned project and an accepted proposal. This is an interim marketplace-level eligibility rule until contract/milestone completion becomes authoritative in the Contract phase.
- PostgreSQL transactional outbox events for freelancer search refreshes.
- Elasticsearch 9.x freelancer projection with monotonic projection versions and lexical/filter search.

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

Integration tests require the corresponding real service. PR CI starts PostgreSQL, Redis, or Elasticsearch only when the impact detector selects that dependency.

## Architecture rules

PostgreSQL is the source of truth. Redis is ephemeral. Elasticsearch is a rebuildable search projection and must not become authoritative business state.

HTTP controllers stay thin: controller → application/domain service → repository/external adapter. Business-state transitions and authorization decisions belong below the route layer.

Marketplace money values are stored as integer minor units plus a three-letter currency code. Proposal versions are append-only through the API. Search updates are written to the PostgreSQL outbox in the same transaction as the source change and indexed asynchronously.

See `docs/adr/` for recorded architectural decisions and `docs/openapi.yaml` for the API contract.
