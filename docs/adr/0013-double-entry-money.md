# ADR 0013: Provider-neutral double-entry Money domain

## Status

Accepted.

## Context

The platform needs milestone funding, release, commission, refunds, wallet views, payouts, and reconciliation. Provider transactions, business contract state, and internal accounting have different failure and retry semantics. Treating a provider balance or a mutable `users.balance` column as authoritative would make replay, refund, payout, and reconciliation bugs difficult to detect or repair.

## Decision

The Money phase uses three separate concepts:

1. Payment provider adapters own provider-specific references, signatures, request/response formats, and retry behavior.
2. PostgreSQL double-entry journals are the internal accounting source of truth.
3. Contract and milestone state describes business entitlement and can change financial state only through Money services.

All amounts are integer minor units paired with a three-letter currency code.

`journal_transactions` and `ledger_entries` are append-only. Every committed journal must contain at least two entries, use exactly one currency, and balance total debits against total credits. PostgreSQL enforces this with deferred constraint triggers, and application services validate before insert. Corrections are new reversal journals.

Milestone escrow is represented by a dedicated ledger account. Funding debits provider clearing and credits milestone escrow. Release debits escrow and credits the freelancer wallet plus platform commission. Wallet balances are derived from ledger entries.

Financial mutations use resource row locks and scoped idempotency records. External provider calls are never treated as the accounting source of truth. Provider webhooks are signature-verified and deduplicated by `(provider, external_event_id)`. Reconciliation compares captured provider transactions with local payment and funding records.

The initial refund operation is deliberately limited to a full refund while the milestone is still `FUNDED`. Partial and dispute-directed settlements belong to the Dispute phase because they require allocation rules not yet present in signed contract terms.

The built-in `sandbox` adapter is deterministic and network-free. Real Stripe/ZarinPal adapters can be added behind the same `PaymentProvider` protocol without leaking provider-specific concepts into business services.

## Consequences

- Duplicate release and payout attempts cannot create duplicate accounting effects.
- Provider retries and duplicate webhooks are harmless when the same idempotency/event identity is reused.
- A failed payout or refund restores internal entitlement through a reversal journal instead of mutating history.
- Operational wallet and escrow views are projections over immutable accounting records.
- PostgreSQL integration tests are mandatory for financial invariants and concurrency.
- Future dispute settlement can post new allocation journals without rewriting prior financial history.
