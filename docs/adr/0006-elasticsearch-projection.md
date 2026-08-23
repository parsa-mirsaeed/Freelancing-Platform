# ADR-0006: Elasticsearch as a search projection

## Status

Accepted.

## Context

Freelancer discovery needs full-text relevance, skill filters, availability filters, and ranking that are better served by Elasticsearch than relational query plans. Search results, however, must never become authoritative marketplace state or participate in contract, payment, authorization, or other correctness decisions.

ADR-0003 defines reliable projection delivery through the PostgreSQL transactional outbox. This ADR defines the storage boundary and read semantics of Elasticsearch itself.

## Decision

PostgreSQL remains the system of record. Elasticsearch contains rebuildable freelancer search documents derived from PostgreSQL state.

The search service writes to a versioned concrete index and reads through a stable alias. Each document carries the freelancer `projection_version`; indexing uses Elasticsearch external version semantics so delayed or duplicated projection work cannot overwrite newer state.

Search documents intentionally denormalize discovery fields such as title, bio, normalized skills, rating, completed-job count, hourly rate, availability, languages, and portfolio text. Search APIs may rank and filter those documents, but any subsequent business mutation must re-authorize and re-read authoritative PostgreSQL entities.

Index loss or schema replacement is recovered by rebuilding a new versioned index from PostgreSQL and switching the alias after the replacement projection is ready.

## Consequences

- Search is eventually consistent by design.
- Elasticsearch downtime may degrade discovery but must not corrupt durable marketplace state.
- Duplicate or out-of-order outbox delivery remains safe because document updates are version-aware and idempotent.
- Index mappings can evolve through versioned rebuilds and alias switches instead of in-place dependence on one index schema.
- Tests that need search correctness use Elasticsearch integration coverage; ordinary domain tests do not require Elasticsearch unless their affected path actually crosses the search boundary.
