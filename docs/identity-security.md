# Identity security hardening

This slice implements the identity/security requirements called out by the platform plan without changing marketplace business state machines.

## Security boundaries

- PostgreSQL remains authoritative for users, sessions, devices, lock state, MFA enrollment, and recovery-code consumption.
- Password verification continues to use Argon2. Login performs a dummy Argon2 verification when the account does not exist so the password path does not reveal account existence through an obvious fast path.
- Failed-login counters are updated while the user row is locked. After the configured threshold, the account is temporarily locked; both wrong-password and locked-account responses remain the same generic `invalid_credentials` response.
- User email is application-encrypted before persistence with AES-256-GCM. Ciphertexts use random nonces and authenticated field context, so equal email addresses do not produce equal ciphertext and ciphertext cannot be moved to another protected field without authentication failure.
- Email lookup and uniqueness use a separate HMAC-SHA-256 blind-index key. The database never needs a decryptable or unkeyed email hash for login lookup.
- `user_devices` stores only SHA-256 fingerprints and user-agent hashes. Session IP addresses are also stored only as hashes for risk/audit correlation. The browser may send a stable opaque device identifier; raw IP addresses and user-agent strings are not persisted by the identity tables.
- TOTP secrets are deterministically derived with HMAC from a random per-user seed plus `MFA_SECRET_KEY`. The database seed alone is not sufficient to calculate a TOTP code. Production should supply a high-entropy `MFA_SECRET_KEY`; it defaults to `SECRET_KEY` for backwards-compatible deployment.
- TOTP enrollment requires the current password, then a valid TOTP code. Enabling MFA creates eight one-time recovery codes. Only keyed hashes of recovery codes are persisted and each recovery code is consumed under a database row lock.
- MFA verification is bound to a `user_sessions` row. A fresh login starts without step-up, and successful TOTP/recovery verification grants a bounded step-up window (`MFA_STEP_UP_TTL_SECONDS`, default 10 minutes).
- Every endpoint protected by `require_roles("admin")` requires recent MFA. Freelancer payout creation independently requires recent MFA before payout business logic or provider interaction executes.

## PII key lifecycle

`PII_ENCRYPTION_KEYS` is an ordered comma-separated keyring. Each entry is `key-id:base64-key`, where each key decodes to exactly 32 bytes. The first entry is the active encryption key; older entries are decrypt-only compatibility keys. Ciphertext stores its key ID, so encryption-key rotation is performed by prepending a new key and retaining older keys until every row has been rewrapped or the retention window has closed. Successful login opportunistically rewraps a user's email under the active key.

`PII_LOOKUP_KEY` is a separate 32-byte key used only for the email blind index. It must not be reused as an encryption key. Rotating this key changes every blind index and therefore requires an explicit coordinated backfill/migration; changing it independently on a running deployment would make existing accounts unfindable. This PR intentionally does not claim transparent lookup-key rotation.

Production must explicitly configure both values. Non-production derives deterministic local-development values from `SECRET_KEY` to keep tests and local migrations usable; those derived values are not a production key-management strategy. Keys belong in the deployment secret store, not source control, container images, logs, audit metadata, or client-visible configuration.

## Audit events

The slice records high-risk identity events including failed/locked/new-device login risk, MFA enrollment start, MFA enablement, successful/failed MFA challenge, and recovery-code use. Existing session registration/refresh/revocation audit events remain intact. Successful login also records whether the user's encrypted email was rewrapped to the current active PII encryption key; no plaintext PII or key material is recorded.

## Failure and retry behavior

- Login failures are safe to retry; counters and temporary lock state are durable.
- TOTP enrollment can be retried before confirmation and returns the same pending enrollment secret for that account.
- A failed MFA challenge does not create step-up state.
- Recovery codes are one-time credentials. A consumed code cannot be replayed; PostgreSQL row locking prevents concurrent successful consumption.
- Failure to authenticate an encrypted PII value is treated as a server-side data/key configuration error and must not be replaced with guessed plaintext.
- Financial idempotency remains unchanged. MFA is checked before payout creation, so a blocked payout never claims or executes its financial idempotency operation.

## Migration and rollback

Migration `0009_identity_security` is additive: it adds nullable security metadata plus new identity tables and a non-null login-attempt counter with a zero default. Existing sessions remain valid but are not MFA-step-up verified.

Migration `0010_pii_encryption` performs the sensitive identity cutover in one PostgreSQL migration transaction: it expands `users` with nullable encrypted-email and blind-index columns, backfills every current row, validates them by making both columns non-null and the blind index unique, then contracts the legacy plaintext email column. This is deliberately **not** a zero-downtime mixed-version migration: old application instances expect `users.email`, while the new application expects the encrypted columns. Deploy it with a coordinated application/migration cutover rather than overlapping old and new application versions. If a future environment requires rolling mixed-version deploys, split the cutover into separate expand/dual-write/backfill/contract releases as described by the platform migration discipline.

Downgrading `0010_pii_encryption` reconstructs the legacy email column by decrypting the stored ciphertext before removing encrypted columns. Therefore all key IDs referenced by database rows must remain available through the rollback window. Never remove an old encryption key merely because a new key is active; first prove no rows reference it and that rollback no longer requires it.

Rollback of `0009_identity_security` is `alembic downgrade 0008_ai_baseline`. Before rollback in an environment where MFA has been required operationally, disable that requirement at the application/release boundary first; downgrading removes MFA/device/recovery metadata and therefore must not be used as an MFA-secret preservation mechanism.

## Configuration

- `PII_ENCRYPTION_KEYS`: ordered AES-256-GCM keyring, for example `2026-08:<base64-32-byte-key>,2026-01:<old-base64-key>`; first key is active.
- `PII_LOOKUP_KEY`: separate base64-encoded 32-byte HMAC key for blind indexes.
- `MFA_SECRET_KEY`: high-entropy server-side key used for TOTP/recovery derivation; defaults to `SECRET_KEY`.
- `MFA_STEP_UP_TTL_SECONDS`: freshness window for sensitive actions; default `600`.
- `AUTH_MAX_FAILED_ATTEMPTS`: failed-password threshold; default `5`.
- `AUTH_LOCK_SECONDS`: temporary lock duration; default `900`.
