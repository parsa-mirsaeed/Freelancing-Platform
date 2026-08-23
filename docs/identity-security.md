# Identity security hardening

This slice implements the identity/security requirements called out by the platform plan without changing marketplace business state machines.

## Security boundaries

- PostgreSQL remains authoritative for users, sessions, devices, lock state, MFA enrollment, and recovery-code consumption.
- Password verification continues to use Argon2. Login performs a dummy Argon2 verification when the account does not exist so the password path does not reveal account existence through an obvious fast path.
- Failed-login counters are updated while the user row is locked. After the configured threshold, the account is temporarily locked; both wrong-password and locked-account responses remain the same generic `invalid_credentials` response.
- `user_devices` stores only SHA-256 fingerprints and user-agent hashes. Session IP addresses are also stored only as hashes for risk/audit correlation. The browser may send a stable opaque device identifier; raw IP addresses and user-agent strings are not persisted by the identity tables.
- TOTP secrets are deterministically derived with HMAC from a random per-user seed plus `MFA_SECRET_KEY`. The database seed alone is not sufficient to calculate a TOTP code. Production should supply a high-entropy `MFA_SECRET_KEY`; it defaults to `SECRET_KEY` for backwards-compatible deployment.
- TOTP enrollment requires the current password, then a valid TOTP code. Enabling MFA creates eight one-time recovery codes. Only keyed hashes of recovery codes are persisted and each recovery code is consumed under a database row lock.
- MFA verification is bound to a `user_sessions` row. A fresh login starts without step-up, and successful TOTP/recovery verification grants a bounded step-up window (`MFA_STEP_UP_TTL_SECONDS`, default 10 minutes).
- Every endpoint protected by `require_roles("admin")` requires recent MFA. Freelancer payout creation independently requires recent MFA before payout business logic or provider interaction executes.

## Audit events

The slice records high-risk identity events including failed/locked/new-device login risk, MFA enrollment start, MFA enablement, successful/failed MFA challenge, and recovery-code use. Existing session registration/refresh/revocation audit events remain intact.

## Failure and retry behavior

- Login failures are safe to retry; counters and temporary lock state are durable.
- TOTP enrollment can be retried before confirmation and returns the same pending enrollment secret for that account.
- A failed MFA challenge does not create step-up state.
- Recovery codes are one-time credentials. A consumed code cannot be replayed; PostgreSQL row locking prevents concurrent successful consumption.
- Financial idempotency remains unchanged. MFA is checked before payout creation, so a blocked payout never claims or executes its financial idempotency operation.

## Migration and rollback

Migration `0009_identity_security` is additive: it adds nullable security metadata plus new identity tables and a non-null login-attempt counter with a zero default. Existing sessions remain valid but are not MFA-step-up verified.

Rollback is `alembic downgrade 0008_ai_baseline`. Before rollback in an environment where MFA has been required operationally, disable that requirement at the application/release boundary first; downgrading removes MFA/device/recovery metadata and therefore must not be used as an MFA-secret preservation mechanism.

## Configuration

- `MFA_SECRET_KEY`: high-entropy server-side key used for TOTP/recovery derivation; defaults to `SECRET_KEY`.
- `MFA_STEP_UP_TTL_SECONDS`: freshness window for sensitive actions; default `600`.
- `AUTH_MAX_FAILED_ATTEMPTS`: failed-password threshold; default `5`.
- `AUTH_LOCK_SECONDS`: temporary lock duration; default `900`.
