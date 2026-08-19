# Frontend

Production-oriented Next.js App Router frontend for the Freelancing Platform backend.

## Requirements

- Node.js 24 LTS
- npm 11
- Flask backend running on `http://localhost:8000` by default

## Run locally

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`.

The frontend uses a backend-for-frontend boundary. Browser JavaScript never receives backend access or refresh tokens. Authentication endpoints exchange credentials server-side, store tokens in HttpOnly cookies, and the `/api/backend/*` route proxies authenticated product requests to Flask.

## Checks

```bash
npm run lint
npm run typecheck
npm run test:unit
npm run build
npm run test:e2e
```

Playwright expects Chromium to be installed. In CI the browser is installed only when the frontend impact map selects E2E coverage.

## Architecture rules

- Backend state machines remain authoritative. The UI must derive available actions from returned state and role, never invent a client-only transition.
- Money is rendered from integer minor units and ISO 4217 currency codes. Formatting uses `Intl.NumberFormat` and the currency's resolved fraction digits.
- Access and refresh tokens are HttpOnly. Do not add localStorage/sessionStorage token persistence.
- Authenticated browser calls use same-origin `/api/backend/*`. Token exchange and provider webhook paths are intentionally blocked from that generic proxy.
- Motion must communicate hierarchy or state and must honor `prefers-reduced-motion`.
- Every interactive control needs keyboard support, visible focus, semantic naming, and a practical touch target.
