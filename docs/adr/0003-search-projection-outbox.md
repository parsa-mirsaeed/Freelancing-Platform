# ADR-0003: Search projection through a PostgreSQL outbox

## Status

Accepted.

## Context

Freelancer search must be fast and independently evolvable, but PostgreSQL remains the authoritative marketplace state. Publishing directly to Elasticsearch from an HTTP request would couple durable writes to search availability and can lose updates if the database commit succeeds while the external publish fails.

## Decision

Marketplace changes that affect freelancer search increment a monotonic `projection_version` and insert a `search.freelancer.refresh` row into `outbox_events` in the same PostgreSQL transaction. A Celery task drains unpublished rows and rebuilds the freelancer document from current PostgreSQL state.

Elasticsearch documents include `projection_version` and use external version checks so an older event cannot overwrite a newer projection. The concrete index is versioned and exposed through an alias so future full reindexing can build a new index before switching the alias.

## Consequences

- Marketplace writes do not fail because Elasticsearch is unavailable.
- Search is eventually consistent and must not be used as authoritative business state.
- Outbox delivery is at-least-once; projection writes therefore remain idempotent.
- Reindex and alias-switch automation can be added without changing marketplace services.
