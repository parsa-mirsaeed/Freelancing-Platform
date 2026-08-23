# ADR-0010: Idempotent financial operations

## Status

Accepted.

## Context

Funding, release, refund, and payout requests can be retried because of client timeouts, worker retries, provider latency, or webhook redelivery. Re-executing a financial mutation can duplicate provider charges or ledger effects, while treating every retry as an error makes safe recovery impossible.

## Decision

Sensitive financial mutations require an `Idempotency-Key` and claim a durable `FinancialIdempotencyKey` record before applying their side effects.

The platform stores a SHA-256 hash of the caller's idempotency key together with the authenticated user, operation name, and a SHA-256 hash of the canonical JSON request payload. Reusing the same key for the same operation and payload resolves to the existing operation record; reusing it with a different payload is rejected as an idempotency conflict.

Claims are protected by the database uniqueness constraint and row locking so concurrent requests converge on one durable record. The completed HTTP status and response body are stored on that record so safe retries can return the already-computed result instead of repeating financial side effects.

The same idempotency key is propagated to mutating payment-provider adapter calls. Provider webhooks are independently deduplicated by their external event identity before they can advance payment or ledger state.

Idempotency complements, rather than replaces, domain state-machine checks, PostgreSQL transactions, immutable double-entry ledger entries, reconciliation, and audit logs.

## Consequences

- Network retries and repeated client submissions do not intentionally duplicate financial mutations.
- A key is scoped to the authenticated user and operation; it cannot be repurposed for a different request payload.
- Concurrent duplicate requests are resolved by durable database constraints rather than process-local memory.
- Provider adapters must support or safely emulate idempotent mutation semantics.
- Tests for financial mutations must cover same-key replay, changed-payload conflict, concurrent claims where relevant, and repeated provider/webhook delivery.
