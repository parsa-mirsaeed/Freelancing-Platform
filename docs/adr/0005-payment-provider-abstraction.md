# ADR-0005: Payment provider abstraction

## Status

Accepted.

## Context

Escrow funding, refunds, payouts, verification, and webhook ingestion depend on external payment providers. Domain services must not encode one provider's SDK types, request shapes, or webhook format because provider availability and regional coverage can change independently of the platform's contract and ledger rules.

## Decision

Payment integrations are accessed through the `PaymentProvider` protocol in `app/payments/providers/base.py`. The platform-facing contract covers payment creation, payment verification, refunds, payouts, transaction lookup, and signed webhook verification. Provider implementations return normalized `ProviderResult` and `VerifiedWebhook` values rather than exposing provider-specific response objects to domain services.

Provider selection is centralized in `app/payments/providers/registry.py`. The repository currently ships a deterministic sandbox provider for development and tests; adding a production provider requires implementing the same protocol and registering it without changing contract, milestone, ledger, or payout state machines.

Idempotency keys are passed through to provider-side mutating operations. Provider webhook signatures are verified by the selected adapter before normalized events enter payment-domain processing.

## Consequences

- Payment-domain state machines and the double-entry ledger remain provider-independent.
- Provider-specific authentication, signatures, references, and API translation stay inside adapters.
- A new provider can be introduced behind configuration and feature flags without duplicating business rules.
- Provider conformance tests are required for mutating operations, webhook verification, and normalized status mapping.
- The abstraction does not make an external provider authoritative: PostgreSQL payment and ledger records remain the platform system of record.
