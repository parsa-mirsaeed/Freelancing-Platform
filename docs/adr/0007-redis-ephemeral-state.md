# ADR-007: Redis is for ephemeral realtime state

## Status

Accepted.

## Decision

Redis stores presence, Socket.IO fan-out metadata, Celery broker state, caches, and rate-limit style ephemeral data. PostgreSQL remains authoritative for conversations, messages, receipts, notifications, contracts, and all financial/business state.

Presence keys use TTLs and may disappear at any time. A Redis loss therefore makes users temporarily appear offline but cannot lose a committed message or business transition.

## Consequences

Realtime code must tolerate Redis reconnects. Durable state is reconstructed from PostgreSQL, and clients recover message gaps through ordered REST pagination.
