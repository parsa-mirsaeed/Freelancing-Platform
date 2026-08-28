# Pre-release and immutable production promotion

The source plan keeps expensive validation out of normal pull requests and requires production to promote the exact image digest that passed main and staging validation. This repository implements that contract with three workflows:

1. `Main` validates merged code, builds one immutable image, scans it, produces an SBOM, records its source SHA and digest, and optionally deploys that exact digest to staging.
2. `Pre-release` accepts only a successful `Main` run, re-runs the expensive release suites against that exact source, verifies staging is running that exact digest, and emits a signed-by-CI attestation artifact only after every gate succeeds.
3. `Release` accepts only a successful `Pre-release` run and re-verifies its attestation against the original `Main` provenance before promoting the exact same digest to production.

No production workflow rebuilds an image.

## Required staging configuration

Before a production candidate can pass `Pre-release`, configure the `staging` GitHub environment with:

- `STAGING_KUBECONFIG_B64` as an environment secret;
- `STAGING_BASE_URL` as an environment variable;
- the normal staging runtime secrets and managed outbound policies described in `docs/stripe-payments.md`;
- `STAGING_DEPLOY_ENABLED=true` so the successful `Main` run actually rolls its digest to every staging workload.

The deployment parity validator requires all checked-in deployments to be part of both staging and production rollout lists. This includes `celery-beat` and the isolated `celery-reconciliation` worker.

## Stripe test-mode acceptance

Stripe remains an external test-mode acceptance step because CI must not contain live payment credentials or silently manufacture a financial production approval. Before dispatching `Pre-release`, complete the twelve-step **Pre-release Stripe test-mode validation** checklist in `docs/stripe-payments.md` and require zero unexplained reconciliation mismatches.

The workflow requires the explicit `stripe_test_mode_validated=true` input. That input is an operator attestation that the external Stripe test-mode checklist was completed for the same staging candidate; it is not a replacement for the checklist.

## Automated pre-release gates

Given the successful `Main` run id, `Pre-release` performs:

- complete backend unit and integration regression with PostgreSQL, Redis, Elasticsearch, Socket.IO and MinIO;
- a full Alembic downgrade/upgrade migration cycle;
- the complete frontend browser suite on Chromium, Firefox and WebKit, including compact mobile coverage;
- a pinned coturn allocation/relay test over UDP and TCP;
- Python and frontend dependency audits plus Bandit and Kubernetes policy validation;
- verification that the successful main run produced the expected SBOM artifact;
- exact-digest verification across every staging deployment;
- liveness, readiness and startup staging smoke checks;
- public API load followed by a 30-minute concurrency soak;
- a full active OWASP ZAP scan against the isolated staging target.

The ZAP full scan performs active attacks. Run this workflow only against an isolated staging environment intended for destructive security testing, never against production.

## Promotion procedure

1. Merge only after the normal required PR gate is green.
2. Wait for the resulting `Main` run to succeed and deploy its digest to staging.
3. Complete the Stripe test-mode checklist for that staging candidate.
4. Dispatch `Pre-release` with that successful `Main` run id and the Stripe confirmation input.
5. Require every pre-release job to succeed. The final job uploads `pre-release-attestation.json` containing the source SHA, image digest, main run id and pre-release run id.
6. Dispatch `Release` with only the successful pre-release run id.
7. `Release` downloads the attestation, verifies the original `Main` run and provenance artifact again, verifies the source commit is on `main`, and promotes the attested digest.

If any digest, run id, source SHA, SBOM, staging workload, test, scan, load threshold or migration check does not match, promotion stops.

## Production environment

The `production` GitHub environment requires:

- `PRODUCTION_KUBECONFIG_B64` as an environment secret;
- `PRODUCTION_BASE_URL` as an environment variable;
- `PRODUCTION_DEPLOY_ENABLED=true`;
- environment protection/reviewer rules appropriate for the organization.

Production rollout updates API, Socket.IO, default workers, Celery Beat, payments, reconciliation, notifications, search and file workers to the same attested digest, waits for every Deployment rollout, then checks all three health endpoints.

## Remaining non-code release gate

E-signature validity, KYC, tax obligations and the legal treatment of customer funds are jurisdiction-dependent. They require legal/compliance approval for the actual launch countries before real-money production is enabled. This repository cannot determine that jurisdiction-specific approval in CI.
