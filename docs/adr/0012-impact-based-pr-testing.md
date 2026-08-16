# ADR 0012: Impact-based pull-request testing

## Status

Accepted.

## Decision

Every pull request runs one always-present `PR Gate / gate` check. A cheap impact detector maps changed paths to affected domains and conditionally runs only required quality, unit, database, Redis, documentation, or image checks.

Unknown paths fail safe by selecting the full core test set. Shared code selects all core unit tests.

## Consequences

The required check never remains pending because an entire workflow was skipped by a path filter. Expensive services start only for changes that can affect them, while shared and unclassified changes receive broader validation.
