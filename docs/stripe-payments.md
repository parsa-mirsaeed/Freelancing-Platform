# Stripe payment provider runbook

The platform keeps provider-specific behavior behind `app/payments/providers/`. PostgreSQL and the double-entry ledger remain the business source of truth. Stripe confirms external money movement but does not replace contract, milestone, escrow, wallet, dispute, or idempotency state.

## Integration shape

Milestone funding uses Stripe-hosted Checkout Sessions for one-time, on-session payments. The browser receives only an authenticated provider action containing a short-lived Stripe Checkout redirect URL. Card and payment-method details never enter the application DOM.

The provider adapter translates Stripe lifecycle events into the existing provider-neutral Money state machine:

- a created Checkout Session is a `PENDING` funding attempt;
- signed successful Checkout events become `payment.captured` only after amount/currency validation;
- failed or expired Checkout events become `payment.failed`;
- unrelated events are stored/deduplicated and ignored safely.

Refunds and connected-account transfers remain behind the same adapter. The core service never imports Stripe resource types.

## Runtime safety gate

`PAYMENT_RUNTIME_ENABLED` is a fail-closed workload switch. When false, provider lookup returns `payment_runtime_disabled` before any external provider operation.

Local development and CI default to the deterministic `sandbox` provider with the payment runtime enabled. Production defaults to the Stripe provider but keeps the payment runtime disabled until an environment explicitly enables it.

A payment-enabled Stripe workload requires:

```text
PAYMENT_RUNTIME_ENABLED=true
PAYMENT_DEFAULT_PROVIDER=stripe
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_CHECKOUT_SUCCESS_URL=https://<web-host>/payments/success?session={CHECKOUT_SESSION_ID}
STRIPE_CHECKOUT_CANCEL_URL=https://<web-host>/payments/cancel
STRIPE_MAX_NETWORK_RETRIES=2
```

A Stripe publishable key is not required for this hosted Checkout integration. Do not expose `STRIPE_SECRET_KEY` or `STRIPE_WEBHOOK_SECRET` through `NEXT_PUBLIC_*` variables.

The frontend normally omits `NEXT_PUBLIC_PAYMENT_PROVIDER`, allowing the backend's validated `PAYMENT_DEFAULT_PROVIDER` to remain authoritative. A public provider override may be used for explicit non-production testing only.

Production Checkout success/cancel URLs must be absolute HTTPS URLs and may not contain embedded credentials or fragments.

## Webhook endpoint

Register the public HTTPS endpoint:

```text
POST https://<api-host>/api/v1/payments/webhooks/stripe
```

Subscribe at minimum to:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `checkout.session.expired`

The endpoint verifies `Stripe-Signature` against the exact raw request body before interpreting the event. Provider event ids are unique per provider. Re-delivery of the same id and payload is a no-op; reuse of an event id with a different payload is rejected.

A synchronous `checkout.session.completed` event funds escrow only when Stripe reports `payment_status=paid`. Deferred payment methods remain pending until `checkout.session.async_payment_succeeded` arrives. Browser redirects and success pages never mark escrow funded.

## Funding idempotency

Every financial mutation requires an application `Idempotency-Key`. The same key is passed to Stripe when creating Checkout Sessions, refunds, and transfers.

A milestone has at most one active `PENDING` funding attempt. A second application key for the same provider reuses that attempt instead of creating a second external payment. Switching providers while an attempt is pending returns `payment_in_progress`.

If Stripe's create-session response is indeterminate because of a connection/API availability failure, the API returns 503 and instructs the caller to retry with the same idempotency key. No local payment intent is committed until the provider reference is known.

## Refund uncertainty

A refund reserves the escrow amount in the ledger before the provider call. Provider timeouts or pending Stripe refunds are not treated as terminal failures:

- the reservation remains `PENDING`;
- the caller retries with the same application idempotency key;
- once a Stripe refund reference exists, retries retrieve that refund instead of creating another;
- escrow is restored only after a terminal provider failure;
- a terminal success returns the milestone to `CREATED` and commits the refund state once.

## Payout destinations

Stripe payout delivery uses verified connected-account ids. Admin routes are protected by the central admin guard, which requires recent MFA.

Configure a freelancer destination with:

```text
PUT /api/v1/admin/freelancers/{freelancer_user_id}/payout-provider-accounts/stripe
{
  "external_account_reference": "acct_..."
}
```

The adapter verifies that the connected account exists and is payout-enabled before the mapping becomes active. Disable it with:

```text
DELETE /api/v1/admin/freelancers/{freelancer_user_id}/payout-provider-accounts/stripe
```

Each payout snapshots its resolved provider destination before wallet funds are reserved. A later mapping change cannot redirect an in-flight idempotent payout.

The current provider operation creates a Stripe transfer to the verified connected account. The platform ledger records the user's internal-wallet entitlement and the transfer request; subsequent external bank payout timing is governed by that connected account's Stripe payout configuration.

An indeterminate provider response leaves the payout reservation `PENDING` and returns 503. It never restores wallet funds merely because the response was lost. Retry with the same idempotency key.

## Reconciliation and Celery retry

The reconciliation job retrieves captured Stripe Checkout Sessions and compares provider amount, currency, status, and the corresponding `milestone_fundings` ledger linkage. Mismatches are persisted, audited, and emitted through the transactional outbox.

Transient Stripe availability failures raise `ProviderTemporaryError`. The payments Celery task retries these failures with bounded exponential backoff and jitter. Reconciliation itself does not create financial side effects, so retries do not duplicate money movement.

## Migration and rollout

Migration `0011_payout_provider_accounts` is expand-only:

- it adds `payout_provider_accounts`;
- it adds a nullable payout destination snapshot;
- it backfills existing sandbox payouts with their deterministic user reference;
- it deliberately keeps the new payout column nullable while old and new application versions may overlap.

New code always snapshots a destination. During a rolling deploy, a legacy sandbox-only pod may still write a null destination; new code upgrades exactly that legacy sandbox row on replay. A real-provider payout with no destination snapshot is treated as invalid state rather than guessed.

A later contract migration may enforce `NOT NULL` only after the previous application version is fully retired and null-row validation is clean.

## Kubernetes / network boundary

The checked-in base manifests remain default-deny and payment-disabled. Stripe activation belongs in the production/staging environment overlay or deployment system:

- set `PAYMENT_RUNTIME_ENABLED=true` only for the API and `celery-payments` workloads that execute provider calls;
- inject Stripe credentials only into those workloads;
- inject the Checkout success/cancel URLs there;
- provide managed outbound TCP/443 access to Stripe using the cluster's egress gateway/proxy or FQDN-aware policy;
- do not grant arbitrary internet egress to notification/search/file/socket workers.

This repository intentionally does not hard-code a production hostname, provider secret, or cluster-specific egress IP policy.

## Pre-release Stripe test-mode validation

Before enabling live mode:

1. Use Stripe test keys only.
2. Configure HTTPS success/cancel URLs in staging.
3. Register the staging webhook and store its `whsec_...` secret in the secret manager.
4. Subscribe to the four Checkout events listed above.
5. Create a test connected account and make it payout-ready.
6. Enable payment runtime and managed Stripe HTTPS egress only for the API and payments worker.
7. Fund a milestone through hosted Checkout and verify exactly one signed webhook creates exactly one funding journal.
8. Replay that webhook and verify no second journal or escrow credit appears.
9. Exercise a deferred/pending provider path and verify no premature escrow funding occurs.
10. Exercise a pre-work refund and same-key retry; verify no duplicate refund and no premature ledger reversal.
11. Release a completed milestone, configure the freelancer connected account, and exercise a payout/transfer.
12. Run reconciliation and require zero unexplained discrepancies before production promotion.
