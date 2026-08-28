# ADR-0019: Transactional outbox for durable side effects

## Status

Accepted.

## Context

Business transactions frequently need to trigger work outside PostgreSQL, including notifications, search projection refreshes, analytics/fraud processing, and other asynchronous consumers. Publishing directly to Redis, Celery, Elasticsearch, or another external system before or after a database commit creates a dual-write failure window: the database can commit while publication fails, or an external side effect can occur for a transaction that later rolls back.

PostgreSQL is the platform system of record. External delivery must therefore be derived from durable committed intent rather than being required for the business transaction to succeed.

## Decision

Domain services that need a durable asynchronous side effect insert an `outbox_events` row in the same SQLAlchemy/PostgreSQL transaction as the authoritative business-state change.

Each outbox event records its event identity/type, aggregate type and ID, payload, creation time, and publication state. The common `enqueue_outbox_event` helper only stages that durable row in the caller's database session; it does not make an external publish part of the business commit.

Outbox dispatch is treated as at-least-once delivery. A dispatcher may retry after process, broker, or network failure, so downstream consumers must be idempotent or deduplicate using stable event/business identities. A consumer must not assume that receiving an event exactly once is guaranteed.

Search indexing remains a projection-specific application of this pattern: consumers rebuild authoritative state from PostgreSQL and reject stale projection versions. Financial authority remains in the ledger/business transaction and is never delegated to outbox delivery.

## Consequences

- A successful business commit preserves the intent to perform required asynchronous work even when Redis/Celery/search is temporarily unavailable.
- A rolled-back business transaction does not leave a committed outbox event for that state change.
- External side effects are eventually consistent and require retry-safe consumers.
- Queue/broker delivery is not a second system of record.
- Critical financial operations must still commit their ledger and business invariants synchronously; the outbox is for follow-up effects, not fire-and-forget financial authority.
