# ADR 0002: PostgreSQL is the system of record

## Status

Accepted.

## Decision

Business state is authoritative in PostgreSQL. Redis is used only for ephemeral/cache/queue concerns. Future Elasticsearch indexes and object storage are projections or binary stores, not authoritative business state.

## Consequences

Business invariants and transaction boundaries remain enforceable in one database. Derived systems must be rebuildable from PostgreSQL and durable event history.
