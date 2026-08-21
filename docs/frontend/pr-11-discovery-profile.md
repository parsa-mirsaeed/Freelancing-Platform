# PR 11: Talent discovery and freelancer profiles

## Scope

This frontend slice maps directly to the Marketplace Core freelancer, portfolio, review, and search APIs. It does not change backend behavior, database schema, search ranking, or authorization.

## Backend contract mapping

### Talent discovery

- `GET /api/v1/search/freelancers`
- Query text uses `q`.
- Skill filters use repeated `skill` query parameters rather than a client-only comma convention.
- Availability is `true`, `false`, or omitted.
- `limit` remains bounded to the backend contract of 1 through 50.
- Search cards render only projection fields supplied by Elasticsearch: professional title, bio, canonical skill slugs, rating, completed jobs, hourly rate, currency, availability, languages, projection version, and projection timestamp.

The frontend does not invent names, avatars, countries, badges, verified status, or other social metadata that the current backend does not expose.

### Public freelancer profile

- `GET /api/v1/freelancers/{user_id}`
- `GET /api/v1/freelancers/{user_id}/portfolio`
- `GET /api/v1/freelancers/{user_id}/reviews`

The three independent reads start in parallel. PostgreSQL-backed profile data remains authoritative even though the discovery list is an Elasticsearch projection.

Portfolio file metadata is displayed only from files already returned by the backend, which currently means files whose scan state is `SAFE`. Upload reservation, scanning progress, and protected download behavior remain owned by the communication/files frontend slice.

### Freelancer profile studio

- `GET /api/v1/freelancers/me/profile`
- `PUT /api/v1/freelancers/me/profile`
- `PUT /api/v1/freelancers/me/availability/rules`
- `PUT /api/v1/freelancers/me/availability/exceptions`
- `POST /api/v1/freelancers/me/portfolio`
- `DELETE /api/v1/portfolio/{item_id}`

A new freelancer can publish the base profile before dependent portfolio or availability requests are enabled. This mirrors the backend requirement that those resources reference an existing freelancer profile.

Hourly rates are entered in major currency units for usability but converted to integer minor units before the request. The conversion uses each ISO currency's actual fraction digits, so zero-decimal and three-decimal currencies are not silently treated as two-decimal currencies. A missing rate always sends both `hourly_rate_minor` and `currency` as null, matching backend validation.

Recurring availability preserves every backend rule, including multiple windows on one weekday. Date exceptions are represented as upserts because the backend does not currently expose an exception-delete endpoint.

## Interaction and accessibility contract

- Search filters are URL-addressable and work with browser navigation and shareable URLs.
- Public pages are server-rendered and do not require authentication.
- Freelancer editing is role-aware in the UI, while backend role/resource authorization remains the security boundary.
- Loading, empty, search-unavailable, profile-not-found, success, and mutation-error states have explicit UI treatment.
- All form controls have programmatic labels, visible focus treatment, keyboard operation, and compact-mobile layouts.
- Motion is limited to non-essential transform/opacity-style affordances and is removed under `prefers-reduced-motion`.

## CI contract

This is a frontend-only slice. The PR gate runs frontend lint, strict TypeScript, selected Vitest coverage, production build, and Chromium critical-flow smoke on desktop and compact-mobile viewports. It does not start PostgreSQL, Redis, Elasticsearch, MinIO, Socket.IO, or backend container jobs because backend runtime code is unchanged.

Browser smoke uses a deterministic local HTTP backend fixture with the same response shapes as the Flask APIs for public server-rendered routes. Authenticated profile mutations are intercepted at the same-origin BFF boundary so browser tests validate the frontend request contract without duplicating backend integration tests.

Critical smoke covers:

- landing and authentication navigation;
- talent discovery and repeated skill filters;
- public freelancer profile, SAFE portfolio metadata, and reviews;
- existing freelancer profile editing;
- removing a published rate without violating the backend rate/currency invariant;
- first-time freelancer profile publication before portfolio exists;
- employer access to the freelancer-only studio.

## Deferred deliberately

- File upload reservation, malware-scanning progress, and protected download URLs: PR 16.
- AI skill suggestions and recommendation explanations: PR 19.
- Full locale routing, translations, and RTL validation: PR 20.
- Employer project creation and gig discovery: PR 12.
