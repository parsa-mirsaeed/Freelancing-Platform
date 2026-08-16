# ADR-0004: Append-only commercial proposal versions

## Status

Accepted.

## Context

Proposal negotiation changes price, delivery, cover letter, and milestone terms. Overwriting the previous values would destroy evidence needed for negotiation history, audit, later contract snapshots, and dispute handling.

## Decision

A `proposals` row stores identity, ownership, state, and the current version number. Every commercial revision creates a new immutable-by-API `proposal_versions` row and optional `proposal_milestones` rows. No endpoint updates or deletes a previous version.

The service layer enforces the marketplace transition graph:

```text
DRAFT → SUBMITTED → UNDER_NEGOTIATION → WITHDRAWN | REJECTED | ACCEPTED
                  ↘ WITHDRAWN | REJECTED | ACCEPTED
```

A database partial unique index prevents more than one accepted proposal for the same project.

## Consequences

- Contract creation can snapshot an explicit accepted proposal version in the next phase.
- Audit and dispute flows retain the exact history of terms.
- Storage grows by revision count, which is intentional and bounded by normal proposal activity.
