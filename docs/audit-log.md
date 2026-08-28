# Audit log integrity

The platform records high-risk actions in the append-only `audit_events` table. Audit rows are immutable at the ORM boundary: update and delete operations are rejected.

## Audit record

An audit row carries:

- actor (`actor_user_id`)
- action
- resource type and resource ID
- timestamp (`created_at`)
- request ID when the action originates from an HTTP request
- `previous_state_hash`
- `new_state_hash`
- bounded metadata appropriate for investigation

The state hashes are SHA-256 fingerprints of canonical JSON snapshots. Keys are sorted and compact JSON separators are used so equivalent object ordering produces the same digest. UUIDs, dates/timestamps, decimal values, and enums have deterministic JSON representations.

Hashes are integrity fingerprints, not encryption. Raw sensitive state must not be copied into audit metadata merely to make a hash available. Callers may hash an in-memory snapshot that contains sensitive values because only the digest is persisted, but metadata must continue to follow the platform's data-minimization rules.

Existing dispute state-change audit events provide real `before` and `after` snapshots in metadata, and the shared audit service hashes those snapshots automatically. Other high-risk producers pass explicit `previous_state` and `new_state` snapshots at their domain boundary so the audit module does not guess business state from action names.

## High-risk coverage

The current implemented high-risk paths with state fingerprints are:

- contract creation, signature, activation, and cancellation
- login-risk state, successful lock reset, MFA enrollment, MFA enablement, MFA verification, failed MFA challenges, and recovery-code consumption
- payout-provider account configuration/replacement and disablement
- payout reservation, provider success, and provider failure/reversal
- milestone release and refund reservation/success/failure
- dispute admin transitions and resolutions through their existing `before`/`after` state snapshots

State snapshots are deliberately minimal. Contract signature-provider references, IP/risk payloads, MFA seeds and recovery codes, payout provider references, and payout destination values are not copied into audit metadata. A payout destination may participate only in the in-memory state hash input so replacement of an active destination changes the integrity fingerprint without adding the destination to the audit record.

The repository currently has no password-change endpoint, admin-impersonation flow, or general permission-management mutation. Those source-plan audit categories therefore have no implemented business action to instrument yet and must be added alongside any future implementation of those capabilities rather than represented by synthetic audit events.

## Rollout and historical rows

Migration `0012_audit_state_hashes` is expand-only. Both hash columns are nullable so old application pods remain compatible during rollout and because historical audit rows cannot be backfilled accurately without reconstructing evidence that was never persisted. New code writes hashes whenever a real state snapshot is available.

A later contract migration may tighten constraints only after all high-risk writers provide snapshots and production validation shows no unexpected nulls. Historical nulls should not be replaced with invented hashes.

## Operational rule

There is no supported product/UI path for deleting audit records. Database retention, archival, and privileged maintenance controls are operational concerns and must not be implemented as ordinary admin CRUD.
