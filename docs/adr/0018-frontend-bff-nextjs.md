# ADR 0018: Next.js frontend with a server-side session boundary

## Status

Accepted.

## Context

The backend exposes bearer access tokens and rotating refresh sessions. A browser frontend needs a modern interactive application without turning JavaScript-readable storage into the long-lived credential authority or duplicating backend authorization rules.

The frontend must also support server-rendered discovery, role-aware workspaces, realtime messaging/calls, international money display, and impact-based CI.

## Decision

Build the frontend under `frontend/` with Next.js App Router and strict TypeScript.

Use a backend-for-frontend boundary for authentication:

- Browser credential submission goes to same-origin Next.js session route handlers.
- Next.js exchanges credentials with Flask server-to-server.
- Access and refresh tokens are stored in HttpOnly, SameSite=Lax cookies; `Secure` is enabled in production.
- Browser JavaScript receives user/session identity but not bearer or refresh tokens.
- Authenticated product calls use `/api/backend/*`, which injects bearer authorization server-side and rotates the refresh session after an upstream 401 when possible.
- Token-exchange endpoints and payment-provider webhook endpoints are blocked from the generic browser proxy.

The backend remains authoritative for authentication, authorization, state transitions, ledger balances, disputes, and model decisions. The frontend can improve affordance but cannot create a client-side substitute for backend policy.

## Consequences

Advantages:

- bearer credentials are not persisted in localStorage or sessionStorage;
- browser API calls are same-origin and do not require a broad CORS policy;
- refresh rotation can be centralized and audited;
- future frontend domains can share one transport/session model;
- Server Components remain available for public and read-heavy surfaces.

Tradeoffs:

- the Next.js server becomes part of the authenticated request path;
- WebSocket authentication needs a deliberate handshake design in the communication/calls PR rather than exposing access tokens globally;
- CSRF-sensitive cookie-backed BFF mutations require same-origin routing and production origin/CSP controls, with explicit verification in the hardening PR;
- deployment must configure `BACKEND_API_URL` as a server-only value.
