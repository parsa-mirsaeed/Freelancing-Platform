# Freelancing Platform

A skill-sharing and freelancing marketplace being built as a domain-driven modular Flask monolith.

## Foundation implemented

- Flask application factory and domain-oriented packages.
- PostgreSQL persistence through SQLAlchemy 2 and Alembic.
- Redis extension and Celery application factory.
- Identity foundation with Argon2 password hashing, access tokens, rotating database-backed refresh sessions, and freelancer/employer self-registration.
- RBAC helpers plus a resource-ownership policy seam.
- Immutable audit events for security-sensitive actions.
- Dependency-free liveness and dependency-aware readiness/startup endpoints.
- OpenAPI 3.1 contract for the initial identity API.
- Non-root production container and local PostgreSQL/Redis Compose stack.
- Impact-based pull-request CI with a single always-present final gate.

## Local development

Create a virtual environment and install the development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Start PostgreSQL and Redis:

```bash
docker compose -f infra/docker/compose.yml up -d postgres redis
```

Apply the schema:

```bash
export DATABASE_URL='postgresql+psycopg://freelancing:freelancing@localhost:5432/freelancing'
export REDIS_URL='redis://localhost:6379/0'
export SECRET_KEY='replace-this-local-secret'
alembic upgrade head
```

Run the API:

```bash
flask --app 'app:create_app()' run --debug
```

## Validation

Fast local checks:

```bash
ruff check app ci tests
ruff format --check app ci tests
mypy app ci
pytest -m unit tests/unit
```

Integration tests require the corresponding real service and environment variable. The PR workflow starts PostgreSQL or Redis only when the impact detector selects them.

## Architecture rules

PostgreSQL is the source of truth. Redis is ephemeral. Future search indexes and object storage remain projections/stores that can be rebuilt or reconciled from authoritative data.

HTTP controllers should remain thin: controller → application/domain service → repository/external adapter. Business-state transitions and authorization decisions belong below the route layer.

See `docs/adr/` for recorded architectural decisions and `docs/openapi.yaml` for the API contract.
