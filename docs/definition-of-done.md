# Definition of Done

A feature or hardening change is done only when the applicable engineering invariants below are satisfied. The pull request must not treat an item as complete merely because the implementation compiles or the aggregate CI gate is green.

## Required engineering checks

1. **Business state machine** — Changed workflow states, allowed transitions, terminal states, and forbidden transitions are explicit. Tests cover important invalid transitions as well as the happy path.
2. **Authorization policy** — Resource ownership, role requirements, and privileged operations are explicit and enforced server-side. Authorization tests cover forbidden access where the change affects access control.
3. **API contract** — Public/backend-for-frontend request and response behavior is documented and validated when an API contract changes. Rolling clients and servers remain compatible when required.
4. **Database constraints** — Persistence-layer constraints protect the changed invariant when application-only validation is insufficient. Do not rely on writable derived balances or other duplicated authorities.
5. **Focused unit tests** — Changed business logic and edge conditions have targeted unit coverage. Tests should be deterministic and scoped to the affected domains.
6. **Critical integration test** — Cross-boundary behavior has an integration test when the change depends on PostgreSQL transactions, Redis/realtime behavior, search projection, object storage, payment-provider semantics, or another integration boundary.
7. **Audit and metrics** — High-risk state changes have appropriate audit records. Operationally important behavior has metrics/logging sufficient to detect failure or drift without recording secrets or unnecessary personal data.
8. **Idempotency for sensitive mutation** — Retriable financial, webhook, notification, or other sensitive mutations cannot duplicate side effects. Idempotency semantics and key scope are explicit where applicable.
9. **Failure and retry behavior** — External-provider failures, asynchronous retries, unknown outcomes, and duplicate delivery are handled deliberately. Retries must not silently convert unknown state into success or duplicate work.
10. **Safe migration** — Database changes are rollout-compatible. Prefer expand → migrate/backfill → switch reads/writes → contract later when mixed application versions may coexist. Historical data must not be fabricated to satisfy a new invariant.
11. **Rollback strategy** — The PR states how to disable or reverse the change and identifies irreversible steps. Database rollback may require a forward repair rather than a destructive downgrade.
12. **Documentation** — Relevant ADRs, API documentation, operational runbooks, or product/engineering docs are updated when behavior or operational responsibility changes.

## Pull request evidence

The pull request template requires explicit **Yes / No** answers for migration, API-contract, payment, security, configuration/secrets, and observability impact. Every **Yes** must include compatibility and validation details. Definition-of-Done items that are genuinely not applicable must be justified in the PR rather than silently omitted.

The impact-based CI gate remains the executable validation layer: only tests and infrastructure checks selected by the affected-domain map should run for a normal PR, while the final `gate` job must be green on the exact PR head before merge.

## Critical-domain review

Payment, ledger, identity/security, infrastructure, and migration paths are owned through `CODEOWNERS`. Payment/ledger migrations should receive a separate specialist review when an eligible specialist reviewer exists. The repository currently has a single maintainer, so enabling mandatory code-owner approval would require that maintainer to approve their own pull request and would deadlock protected-branch merges. Do not create synthetic teams or bypass rules to simulate separation of duties; enable the additional reviewer requirement when a distinct qualified reviewer or team is available.
