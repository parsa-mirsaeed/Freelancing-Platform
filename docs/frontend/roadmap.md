# Frontend engineering roadmap

The frontend is implemented in reviewable vertical slices that mirror backend domain boundaries. Each PR must keep the backend as the source of truth and add only the tests selected by the changed surface.

## Product and engineering standards

- Next.js App Router with React Server Components by default and client components only for genuine interaction.
- Node.js 24 LTS and current stable Next.js 16.x.
- TypeScript strict mode with unchecked-index protection and no implicit fallthrough.
- WCAG 2.2 AA target, semantic HTML, WAI-ARIA patterns only where native semantics are insufficient, visible focus, keyboard operation, and 44px-class touch targets.
- Responsive layouts from 320px upward with desktop, tablet, and compact mobile behavior.
- `prefers-reduced-motion` is mandatory. Motion is limited to transform/opacity or state transitions where possible.
- BCP 47 locale-ready formatting through platform `Intl` APIs. Currency rendering uses ISO 4217 codes and the currency's actual fraction digits.
- Backend authorization and state machines remain authoritative. Hiding a control in the client is never treated as an authorization boundary.
- Backend access and refresh tokens remain server-side in HttpOnly cookies behind a same-origin backend-for-frontend proxy.
- No optimistic success for money, signatures, dispute resolution, or other irreversible/high-impact mutations. UI success follows authoritative backend confirmation.
- Core Web Vitals budgets for production: LCP <= 2.5s, INP <= 200ms, CLS <= 0.1 at p75 for supported production traffic.
- All loading, empty, error, stale, unauthorized, forbidden, conflict, and retry states must be designed—not left as raw JSON or generic spinners.

## PR sequence

### PR #10 — Frontend foundation, design system, authentication boundary

- Next.js application scaffold and strict TypeScript/ESLint/Vitest/Playwright setup.
- Modern public landing surface, responsive navigation, auth screens, role-aware dashboard shell, error and not-found states.
- Design tokens, typography hierarchy, layout primitives, accessible focus behavior, reduced-motion handling, and lightweight motion primitives.
- Secure BFF session exchange with HttpOnly access/refresh cookies and an authenticated same-origin product API proxy.
- International money/date formatting primitives.
- Frontend-aware impact detection and conditional frontend/E2E jobs in the existing aggregate PR gate.

### PR #11 — Discovery, freelancer profile, availability, portfolio, reviews

Backend mapping:

- `GET /search/freelancers`
- `GET/PUT /freelancers/me/profile`
- `GET /freelancers/{user_id}`
- availability rules and exceptions
- portfolio list/create/delete
- freelancer review list

User experience:

- Search-first talent discovery with query/skill/availability filters and URL-addressable state.
- Public profile with professional summary, skills, languages, rate, availability, portfolio, and reviews.
- Freelancer profile editor with timezone-aware availability and explicit save/error states.
- Portfolio editing with safe file state integrated when the file PR lands.

### PR #12 — Gigs and projects

Backend mapping:

- gigs list/read/create/update
- projects list/read/create/update/close

User experience:

- Public gig discovery and package comparison for Basic/Standard/Premium.
- Freelancer service builder with price, delivery, revision, requirement, and active-state validation.
- Employer project creation/editing with budget, currency, skills, and clear lifecycle state.
- Role-specific workspace navigation and empty states.

### PR #13 — Proposals and negotiation

Backend mapping:

- create/list/read proposals
- append immutable proposal versions
- submit/negotiate/withdraw/reject/accept transitions

User experience:

- Freelancer proposal composer with milestone terms.
- Employer comparison workspace designed for side-by-side commercial review.
- Negotiation timeline that preserves historical versions instead of overwriting terms.
- State-aware action bar showing only backend-valid transitions.

### PR #14 — Contracts and milestone execution

Backend mapping:

- project contract and contract detail
- signing with `Idempotency-Key` and document hash
- cancellation
- milestone detail/start/submit/request-changes/approve

User experience:

- Immutable contract review with parties, snapshot, hash, signatures, and current status.
- Deliberate signing confirmation; no ambiguous one-click destructive action.
- Milestone timeline and progress workspace mirroring the backend state machine.
- Submission/change-request notes and completion eligibility.

### PR #15 — Money, escrow, wallet, payouts

Backend mapping:

- milestone financial state, fund, release, refund
- wallet
- payouts

User experience:

- Ledger-derived escrow status and funding call-to-action.
- High-impact money confirmations with exact amount/currency and idempotency keys.
- Freelancer wallet grouped by currency with explicit available/reserved semantics from backend responses.
- Payout flow with no client-side balance authority.

### PR #16 — Communication, files, notifications

Backend mapping:

- conversations and cursor-based messages
- delivery/read receipts
- presigned upload reservation/complete/download
- notifications and notification preferences

User experience:

- Desktop two-pane and mobile conversation workroom.
- Optimistic message composition only after durable POST acknowledgement rules are respected.
- Attachment lifecycle: reserving, uploading, scanning, safe/rejected, downloadable.
- Notification center and channel preferences with unread/read state.

### PR #17 — WebRTC calls

Backend mapping:

- ICE server credentials and durable call state
- Socket events: invite, accept, SDP offer/answer, ICE candidate, end

User experience:

- One-to-one voice/video call surface with preflight device controls.
- Peer-to-peer media, Redis-backed signaling transport, and durable call state reconciliation.
- Screen-share renegotiation where supported.
- Explicit permission, unavailable-device, TURN failure, reconnect, and ended states.

### PR #18 — Disputes and arbitration

Backend mapping:

- open/read dispute
- attach SAFE evidence
- administrator transitions
- release/refund/split resolution

User experience:

- Party-facing dispute timeline with frozen milestone state and evidence submission.
- Admin review surface separated from ordinary member navigation.
- Resolution composer that makes release/refund/split arithmetic legible before confirmation.
- Terminal outcomes cannot be visually represented as reversible actions.

### PR #19 — AI recommendations, pricing, skills, risk administration

Backend mapping:

- project freelancer recommendations and attribution events
- skill suggestions
- project price estimate
- model registry
- explainable risk assessment and human CLEAR/ESCALATE review

User experience:

- Recommendation explanations and ranking reasons without pretending statistical certainty.
- Skill suggestions are user-confirmed suggestions, never silent profile mutations.
- Price ranges communicate source/fallback/insufficient-data states.
- Admin risk review shows evidence and reasons; it never presents the score as an automatic ban/payment decision.

### PR #20 — Internationalization, accessibility, performance, release UX

- Locale architecture and RTL-ready layout primitives without hard-coding one translation direction into domain components.
- Full WCAG 2.2 AA keyboard/screen-reader audit of critical workflows.
- Browser matrix and critical-path E2E across role workflows.
- Bundle and Core Web Vitals budgets; route-level lazy loading for heavy call/admin surfaces.
- Frontend container/deployment wiring, same-digest promotion rules, CSP production policy, observability, and synthetic critical-flow checks.

## CI discipline

Each frontend PR keeps the existing single aggregate `PR Gate / gate` contract. The impact detector emits frontend flags plus selected unit/E2E targets. Frontend quality/build always runs for affected frontend code; Playwright runs only for mapped critical user flows; backend PostgreSQL/Redis/Elasticsearch/MinIO jobs remain off unless the PR also changes backend code that requires them.
