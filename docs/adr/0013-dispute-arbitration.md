# ADR-0013: Dispute arbitration consumes escrow atomically

## Status

Accepted.

## Context

Dispute handling crosses contract authorization, milestone state, managed evidence, provider refunds,
the internal double-entry ledger, notifications, and administrator audit. A dispute must freeze normal
milestone release without introducing a second mutable balance or a side channel around the Money
invariants.

## Decision

- A milestone may have at most one dispute record.
- Opening a dispute uses the same PostgreSQL `FOR UPDATE` milestone lock as financial release and moves
  the milestone to `DISPUTED`; whichever concurrent operation acquires the row first determines whether
  release or dispute opening succeeds.
- Parties are snapshotted into `dispute_parties`; evidence rows, events, and decisions are immutable.
- Only SAFE managed files with purpose `DISPUTE_EVIDENCE`, owned by a dispute party, can be submitted.
- Administrator review uses the explicit `OPEN -> EVIDENCE_COLLECTION -> UNDER_REVIEW` path, with
  `NEED_MORE_INFO` returning to evidence/review. `RESOLVED` is only entered through the financial
  resolution service.
- Resolution outcomes are `RELEASE_TO_FREELANCER`, `REFUND_CLIENT`, and `SPLIT`.
- Every resolution consumes the complete funded escrow amount in one `DISPUTE_RESOLUTION` double-entry
  journal. A split must total the funded amount exactly. Commission applies only to the freelancer's
  gross award.
- Any provider refund is issued with a deterministic provider idempotency key before the database
  decision is committed. The confirmed refund is persisted alongside the same resolution journal.
- Resolved financial settlements move the milestone to the existing terminal `RELEASED` state; the
  dispute decision remains the authoritative record of how the escrow was distributed.
- All administrator transitions and decisions write immutable audit metadata containing who, what,
  when, why, and before/after state.

## Consequences

Normal release and dispute freeze cannot both commit for the same funded milestone. Split/refund/release
arbitration remains reconcilable through the same ledger used by normal Money operations, and no
standalone dispute balance can diverge from escrow. Provider integrations must preserve idempotent partial
refund semantics for dispute splits.
