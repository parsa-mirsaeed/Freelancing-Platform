# ADR-0011: Contract Snapshotting

## Status

Accepted.

## Context

Projects and proposal versions remain mutable during marketplace negotiation. An accepted commercial agreement must not later change because a project description, proposal, attachment row, or future pricing policy changes. The platform also needs an auditable signature boundary and milestone values that can be proven to match the agreement that was signed.

## Decision

Accepting a proposal creates exactly one `Contract` for the project in the same PostgreSQL transaction as the proposal transition. Contract Version 1 snapshots the accepted proposal's current version, project scope, attachment metadata, price in integer minor units, currency, delivery days, and milestones. The canonical JSON snapshot is SHA-256 hashed and that hash is stored on the contract version.

`ContractVersion`, `ContractSignature`, and `MilestoneEvent` rows are append-only. SQLAlchemy listeners reject application-level update/delete attempts, and PostgreSQL triggers reject direct database mutation. If contract terms ever change, the application must create a new contract version rather than edit a signed snapshot.

The employer and freelancer are both required contract parties. A signature is bound to the current contract version's document hash and stores signed time, user, request IP/user-agent metadata, risk metadata, an optional external signature-provider reference, and a hashed idempotency key. A contract becomes `ACTIVE` only after every required party has signed the same current version.

Milestone commercial values are copied from the accepted proposal version into Contract Version 1 and must equal the snapshot. The Contract phase exposes only execution progress transitions after funding: freelancer start/submit and employer request-changes/approve. The Money phase owns `CREATED -> FUNDED` and `APPROVED -> RELEASE_PENDING -> RELEASED`; this avoids introducing payment or ledger authority before financial invariants exist.

The engineering plan requires commission, refund terms, and dispute terms to be represented in the snapshot but does not define product values for them. Version 1 therefore keeps explicit `null` placeholders for those policy slots rather than inventing financial/legal rules. Once those policies are defined, an unsigned contract may be superseded by a new version; signed terms must never be rewritten in place.

## Consequences

- Proposal acceptance and contract creation fail atomically.
- A project has at most one contract and an accepted proposal can back at most one contract.
- Both signatures are required before work progress can advance.
- Contract and signature history is immutable at both ORM and PostgreSQL boundaries.
- Payment funding, release, commission, refunds, disputes, KYC/tax, and jurisdiction-specific e-signature validity remain outside this phase and require their own policy and production review.
