# ADR-008: Scale Socket.IO through Redis-backed rooms

## Status

Accepted.

## Decision

Socket.IO instances use the shared Redis message queue. Rooms are scoped as `user:{user_id}`, `conversation:{conversation_id}`, and `contract:{contract_id}`.

A message send is authenticated and authorized, deduplicated by `client_message_id`, assigned a per-conversation sequence under a database lock, persisted together with outbox events, and committed before ACK or broadcast. A broadcast failure after commit is recoverable because reconnecting clients fetch messages after their last sequence.

Presence is Redis-only with TTL refresh and is not written to PostgreSQL on every heartbeat.

## Verification

The realtime integration test starts two independent Socket.IO server processes sharing Redis and verifies that a committed message sent through one process reaches a client connected to the other.
