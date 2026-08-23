"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import {
  confirmMfaEnrollment,
  getMfaStatus,
  hasFreshMfa,
  startMfaEnrollment,
  verifyMfa,
  type MfaEnrollment,
  type MfaStatus,
} from "@/lib/api/security";

import styles from "./security.module.css";

export function SecurityWorkspace() {
  const { user, status: sessionStatus } = useSession();
  const [mfa, setMfa] = useState<MfaStatus | null>(null);
  const [enrollment, setEnrollment] = useState<MfaEnrollment | null>(null);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (sessionStatus !== "authenticated" || !user) return;
    const controller = new AbortController();
    void getMfaStatus(controller.signal)
      .then(setMfa)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Unable to load security status.");
        }
      });
    return () => controller.abort();
  }, [sessionStatus, user]);

  async function refresh() {
    const next = await getMfaStatus();
    setMfa(next);
    return next;
  }

  async function beginEnrollment() {
    if (!password) {
      setError("Enter your current password before starting MFA enrollment.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      setEnrollment(await startMfaEnrollment(password));
      setPassword("");
      setMessage("Enrollment started. Add the secret to your authenticator, then confirm a code.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to start MFA enrollment.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmEnrollment() {
    if (!code.trim()) {
      setError("Enter the six-digit code from your authenticator.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await confirmMfaEnrollment(code);
      setRecoveryCodes(result.recovery_codes);
      setEnrollment(null);
      setCode("");
      await refresh();
      setMessage("MFA is enabled and this session is freshly verified.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to confirm MFA enrollment.");
    } finally {
      setBusy(false);
    }
  }

  async function stepUp() {
    if (!code.trim()) {
      setError("Enter an authenticator code or an unused recovery code.");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await verifyMfa(code);
      setCode("");
      const next = await refresh();
      setMessage(
        result.recovery_code_used
          ? `Recovery code accepted. ${next.recovery_codes_remaining} recovery codes remain.`
          : "This session is freshly verified for sensitive actions.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "MFA verification failed.");
    } finally {
      setBusy(false);
    }
  }

  if (sessionStatus === "loading") {
    return (
      <main className={styles.page}>
        <section className={styles.state} role="status">
          Checking security session…
        </section>
      </main>
    );
  }

  if (sessionStatus !== "authenticated" || !user) {
    return (
      <main className={styles.page}>
        <section className={styles.state}>
          <h1>Sign in to manage account security.</h1>
          <p>MFA enrollment and session step-up are available only to an authenticated account.</p>
          <Link href="/login?next=/dashboard/security">Sign in securely</Link>
        </section>
      </main>
    );
  }

  const fresh = mfa ? hasFreshMfa(mfa) : false;
  const sensitiveRole = user.roles.includes("admin") || user.roles.includes("freelancer");

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div>
          <Link href="/dashboard">← Dashboard</Link>
          <span>Account protection</span>
          <h1>Security & MFA</h1>
          <p>
            MFA is enforced by Flask on admin actions and payout creation. This page only manages
            enrollment and a temporary session-bound step-up; browser role checks are not a security
            boundary.
          </p>
        </div>
        <aside>
          <span>Current account</span>
          <strong>{user.email}</strong>
          <p>
            {sensitiveRole
              ? "Sensitive actions require MFA."
              : "MFA is available for this account."}
          </p>
        </aside>
      </section>

      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className={styles.success} role="status">
          {message}
        </p>
      ) : null}

      <section className={styles.panel} aria-labelledby="mfa-heading">
        <div className={styles.heading}>
          <div>
            <span>Session-bound step-up</span>
            <h2 id="mfa-heading">Multi-factor authentication</h2>
          </div>
          <p>
            A fresh login is not automatically step-up verified. Sensitive operations require a
            recent authenticator or recovery-code challenge on this exact backend session.
          </p>
        </div>

        {!mfa ? (
          <p role="status">Loading MFA status…</p>
        ) : !mfa.enabled ? (
          <div className={styles.flow}>
            {!enrollment ? (
              <>
                <p>MFA is not enabled. Confirm your current password before creating a TOTP secret.</p>
                <label>
                  <span>Current password</span>
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    disabled={busy}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </label>
                <button type="button" disabled={busy} onClick={() => void beginEnrollment()}>
                  {busy ? "Starting…" : "Start authenticator setup"}
                </button>
              </>
            ) : (
              <>
                <div className={styles.secretBox}>
                  <span>Authenticator secret</span>
                  <code>{enrollment.secret}</code>
                  <small>
                    Add this secret manually to a TOTP authenticator. The provisioning URI is shown
                    below for clients that support it.
                  </small>
                  <code className={styles.uri}>{enrollment.otpauth_uri}</code>
                </div>
                <label>
                  <span>Six-digit authenticator code</span>
                  <input
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    value={code}
                    disabled={busy}
                    onChange={(event) => setCode(event.target.value)}
                  />
                </label>
                <button type="button" disabled={busy} onClick={() => void confirmEnrollment()}>
                  {busy ? "Confirming…" : "Confirm and enable MFA"}
                </button>
              </>
            )}
          </div>
        ) : (
          <div className={styles.flow}>
            <div className={fresh ? styles.fresh : styles.challenge}>
              <strong>{fresh ? "Session step-up is fresh" : "Session step-up required"}</strong>
              <span>
                {fresh && mfa.verified_until
                  ? `Sensitive access remains verified until ${new Date(
                      mfa.verified_until,
                    ).toLocaleString()}.`
                  : "Verify this session before an admin action or payout request."}
              </span>
            </div>
            <p>{mfa.recovery_codes_remaining} unused recovery codes remain.</p>
            <label>
              <span>Authenticator or recovery code</span>
              <input
                autoComplete="one-time-code"
                value={code}
                disabled={busy}
                onChange={(event) => setCode(event.target.value)}
              />
            </label>
            <button type="button" disabled={busy} onClick={() => void stepUp()}>
              {busy ? "Verifying…" : "Verify this session"}
            </button>
          </div>
        )}
      </section>

      {recoveryCodes.length ? (
        <section className={styles.panel} aria-labelledby="recovery-heading">
          <div className={styles.heading}>
            <div>
              <span>Shown once</span>
              <h2 id="recovery-heading">Save your recovery codes</h2>
            </div>
            <p>
              Store these codes outside this application. The backend persists only keyed hashes and
              cannot show these plaintext values again.
            </p>
          </div>
          <ul className={styles.codes}>
            {recoveryCodes.map((recoveryCode) => (
              <li key={recoveryCode}>
                <code>{recoveryCode}</code>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  );
}
