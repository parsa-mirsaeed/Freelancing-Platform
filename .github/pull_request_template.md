## What changed?

Describe the behavior or implementation change and why it is needed.

## Affected domains

List only the product, platform, data, or operational domains affected by this PR.

## Risk and contract answers

Answer every item with **Yes** or **No**. For every **Yes**, explain the impact, compatibility strategy, and validation below.

- DB migration? **Yes / No**
- API contract changed? **Yes / No**
- Payment behavior changed? **Yes / No**
- Security impact? **Yes / No**
- New config/secrets? **Yes / No**
- Observability added/changed? **Yes / No**

## Migration / compatibility strategy

For schema or externally visible contract changes, describe the safe rollout sequence. Prefer expand → migrate/backfill → switch reads/writes → contract later when a rolling deployment requires it. Write `Not applicable` when there is no migration or compatibility concern.

## Rollback strategy

State the rollback boundary explicitly: application rollback, feature-flag disablement, forward database repair, provider/runtime rollback, or another concrete mechanism. Call out any irreversible step.

## Tests added or updated

List only tests required by the affected domains and critical invariants. Do not add unrelated broad suites solely for this PR.

## Definition of Done

Use [docs/definition-of-done.md](../docs/definition-of-done.md). Check each applicable requirement; when a requirement is not applicable, state why below instead of silently skipping it.

- [ ] Business state machine is explicit for changed workflow behavior, or N/A is justified.
- [ ] Authorization policy is explicit and tested where access changes.
- [ ] API contract is updated/validated where the public or BFF contract changes.
- [ ] Database constraints preserve changed data invariants where persistence changes.
- [ ] Focused unit tests cover changed logic.
- [ ] Critical integration tests cover changed cross-boundary behavior where applicable.
- [ ] Appropriate audit events and/or metrics cover high-risk or operationally relevant behavior.
- [ ] Sensitive mutations are idempotent where retries can duplicate side effects.
- [ ] Failure and retry behavior is defined and tested where external or asynchronous work is involved.
- [ ] Database migration is safe for rollout/rollback where a migration exists.
- [ ] Rollback strategy is documented above.
- [ ] Relevant documentation is updated.

### N/A justification / reviewer notes

Explain any unchecked Definition-of-Done item and any specialist-review requirement that cannot be satisfied by the current reviewer pool.
