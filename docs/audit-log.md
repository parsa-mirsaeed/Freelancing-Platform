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

Existing dispute state-change audit events already provide real `before` and `after` snapshots in metadata. The shared audit service hashes those snapshots automatically. Other high-risk producers should pass explicit `previous_state` and `new_state` snapshots to `record_audit_event`; that coverage is kept at the domain boundary so the audit module does not guess business state from action names.

## Rollout and historical rows

Migration `0012_audit_state_hashes` is expand-only. Both hash columns are nullable so old application pods remain compatible during rollout and because historical audit rows cannot be backfilled accurately without reconstructing evidence that was never persisted. New code writes hashes whenever a real state snapshot is available.

A later contract migration may tighten constraints only after all high-risk writers provide snapshots and production validation shows no unexpected nulls. Historical nulls should not be replaced with invented hashes.

## Operational rule

There is no supported product/UI path for deleting audit records. Database retention, archival, and privileged maintenance controls are operational concerns and must not be implemented as ordinary admin CRUD.
