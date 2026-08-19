# ADR 0014: WebRTC Signaling and TURN Boundary

## Status

Accepted.

## Context

The Communication phase already provides authenticated Socket.IO connections, Redis-backed
multi-instance broadcast, and durable one-to-one contract conversations. The WebRTC phase
needs voice, video, and screen sharing without turning the Flask application into a media
server or introducing a premature conferencing architecture.

## Decision

For this phase:

- `CallSession` is durable PostgreSQL business state with `INVITED -> ACTIVE -> ENDED`.
- Calls are restricted to conversations with exactly two members.
- Socket.IO carries signaling only: `call.invite`, `call.accept`, `webrtc.offer`,
  `webrtc.answer`, `webrtc.ice_candidate`, and `call.end`.
- SDP and ICE candidate payloads are bounded, authorized, relayed to the peer, and never
  persisted.
- Media remains browser-to-browser WebRTC. Voice and video use the same peer connection.
  Screen sharing is a WebRTC track replacement/renegotiation and does not create a server
  media path.
- ICE configuration is exposed through an authenticated REST endpoint.
- TURN credentials are HMAC-derived from an expiry timestamp, user id, and authenticated
  session id. They are short-lived and capped at one hour.
- Production must configure TURN URLs and a non-default shared secret. A coturn-compatible
  TURN REST credential scheme is used.
- Only one invited or active call may exist per conversation; PostgreSQL row locking plus a
  partial unique index enforce the invariant under concurrency.
- Invite, accept, and end transitions are audit logged. High-volume offer/answer/ICE payloads
  are deliberately excluded from the audit log.
- Group calling is out of scope. If serious 3+ participant calls are added, use an SFU such
  as mediasoup or Janus instead of making mesh P2P the conference architecture.

## Consequences

The application owns authorization and call lifecycle but not media transport. Redis remains
ephemeral signaling infrastructure, PostgreSQL remains the system of record for call state,
and TURN can be scaled independently. Failed signaling delivery does not corrupt durable call
state; clients may retry signaling while the call remains active.

## Configuration

The Calls domain reads these deployment settings without broadening shared application
configuration impact:

- `STUN_URLS`
- `TURN_URLS`
- `TURN_SHARED_SECRET`
- `TURN_CREDENTIAL_TTL_SECONDS`

Development defaults point to localhost. Production must provide a real TURN service and
secret.

## Rollback

The signaling handlers and Calls blueprint can be disabled while preserving historical
`call_sessions`. Migration `0007_calls` is additive and can be rolled back only after call
traffic is disabled and retained call history is no longer required.
