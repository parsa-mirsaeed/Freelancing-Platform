# ADR 0001: Modular monolith

## Status

Accepted.

## Decision

Start as a Flask modular monolith with explicit domain packages. HTTP controllers delegate to application/domain services, which own policy and persistence orchestration. Domain boundaries must not depend on transport-specific details.

## Consequences

The first release keeps operational complexity low while preserving extraction seams for payments, realtime, search, and recommendations if their scaling or reliability needs later justify separate services.
