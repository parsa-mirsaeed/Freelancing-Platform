# Stripe payment provider runbook

The platform keeps provider-specific behavior behind `app/payments/providers/`. PostgreSQL and the double-entry ledger remain the business source of truth; Stripe confirms external money movement but does not replace contract, milestone, escrow, wallet, or dispute state.

## Why this adapter uses PaymentIntents

Stripe recommends Checkout Sessions for most straightforward one-time payment integrations. This platform uses the PaymentIntents lifecycle intentionally because milestone funding already has a provider-neutral escrow state machine, idempotency store, signed webhook ingestion, reconciliation, refund workflow, and browser action boundary. The adapter contains Stripe-specific lifecycle details so the core Money domain remains provider-neutral.

## Runtime configuration

Local development and CI default to the deterministic `sandbox` provider.

Production workloads that are allowed to execute provider calls must set:

```text
PAYMENT_RUNTIME_ENABLED=true
PAYMENT_DEFAULT_PROVIDER=stripe
STRIPE_SECRET_KEY=...
STRIPE_PUBLISHABLE_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_MAX_NETWORK_RETRIES=2
```

Production workloads that do not execute payment-provider calls should leave `PAYMENT_RUNTIME_ENABLED=false` and should not receive Stripe secrets. This limits secret exposure across specialized workers.

The browser build selects the provider independently:

```text
NEXT_PUBLIC_PAYMENT_PROVIDER=stripe
```

Never expose `STRIPE_SECRET_KEY` or `STRIPE_WEBHOOK_SECRET` through `NEXT_PUBLIC_*` variables. The authenticated payment-action endpoint returns only the publishable key and the PaymentIntent client secret needed by the owning employer. The client secret is not persisted in financial idempotency responses or audit metadata.

## Webhook endpoint

Register the public HTTPS endpoint:

```text
POST https://<api-host>/api/v1/payments/webhooks/stripe
```

Subscribe at minimum to:

- `payment_intent.succeeded`
- `payment_intent.payment_failed`

The endpoint verifies the `Stripe-Signature` header against the exact raw request body before parsing the event. Provider event ids are unique per provider. Re-delivery of the same id and payload is a no-op; reuse of an event id with a different payload is rejected.

Escrow is funded only after the signed success event passes amount/currency checks and commits the corresponding balanced journal transaction. Browser confirmation never marks escrow funded by itself.

## Funding idempotency

Every financial mutation requires an application `Idempotency-Key`. Stripe create/refund/transfer requests receive the same key at the provider boundary.

A milestone may have only one active `PENDING` funding attempt. The milestone row lock serializes concurrent funding requests. A second key for the same provider reuses the existing provider reference instead of creating a second charge; switching providers while an attempt is pending returns `payment_in_progress`.

## Refund uncertainty

A provider timeout is not treated as a failed refund. The ledger reservation remains pending and the caller retries with the same application idempotency key. Once Stripe has returned a refund reference, retries retrieve that refund rather than creating another one. Escrow is restored only after a terminal provider failure.

## Payout destinations

Stripe payouts use verified connected-account ids. Admin access already requires recent MFA. Configure a freelancer destination with:

```text
PUT /api/v1/admin/freelancers/{freelancer_user_id}/payout-provider-accounts/stripe
{
  "external_account_reference": "acct_..."
}
```

The adapter verifies the connected account exists and is payout-enabled before storing it. Disable the mapping with:

```text
DELETE /api/v1/admin/freelancers/{freelancer_user_id}/payout-provider-accounts/stripe
```

Each payout snapshots its resolved provider destination before wallet funds are reserved. Changing the account mapping later cannot redirect an in-flight idempotent payout.

A provider network outcome that is unknown leaves the payout reservation `PENDING`; it does not restore wallet funds. Retry with the same idempotency key.

## Reconciliation

The existing reconciliation job retrieves captured Stripe PaymentIntents and compares provider amount, currency, status, and the corresponding `milestone_fundings` ledger linkage. Mismatches are persisted, audited, and emitted through the transactional outbox for operational alerting.

Run reconciliation with the existing payment task/worker only from a payment-enabled workload.

## Kubernetes / network boundary

The checked-in namespace remains default-deny. Do not add unrestricted internet egress to every worker. The production environment must provide managed HTTPS egress for the payment-enabled API/payment worker to Stripe endpoints, normally through the cluster's egress gateway/proxy or an environment-specific FQDN-aware policy.

Only payment-enabled workloads need the Stripe secrets from `freelancing-runtime-secrets`.

## Pre-release sandbox validation

Before enabling Stripe in production:

1. Use Stripe test/sandbox keys only.
2. Create a test connected account and make it payout-ready.
3. Register the HTTPS webhook endpoint and store its `whsec_...` secret in the staging secret manager.
4. Enable managed Stripe HTTPS egress for the payment-enabled workload.
5. Build the frontend with `NEXT_PUBLIC_PAYMENT_PROVIDER=stripe`.
6. Fund a milestone through Stripe test payment UI and verify a signed webhook creates exactly one funding journal.
7. Replay the webhook and verify no second journal or escrow credit appears.
8. Exercise a pre-work refund and verify retrying the same key does not create a second refund.
9. Release a completed milestone, configure the freelancer test connected account, and exercise a payout.
10. Run reconciliation and require zero unexplained discrepancies before production promotion.
