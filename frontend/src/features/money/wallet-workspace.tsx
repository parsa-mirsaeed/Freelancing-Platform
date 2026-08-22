"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import {
  CURRENT_PAYMENT_PROVIDER,
  getWallet,
  requestPayout,
  type PayoutResult,
  type WalletBalances,
} from "@/lib/api/money";
import { formatMinorMoney, majorMoneyInputToMinor, minorMoneyInputValue } from "@/lib/intl";

import styles from "./money.module.css";

export function WalletWorkspace() {
  const { user, status } = useSession();
  const [wallet, setWallet] = useState<WalletBalances | null>(null);
  const [currency, setCurrency] = useState("");
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [lastPayout, setLastPayout] = useState<PayoutResult | null>(null);
  const payoutKey = useRef<string | null>(null);

  const isFreelancer = Boolean(user?.roles.includes("freelancer"));

  useEffect(() => {
    if (status !== "authenticated" || !user || !isFreelancer) return;
    const controller = new AbortController();
    void getWallet(controller.signal)
      .then((next) => {
        setWallet(next);
        const currencies = Object.keys(next.balances).sort();
        setCurrency((current) => current || currencies[0] || "");
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load wallet balances.");
      });
    return () => controller.abort();
  }, [isFreelancer, status, user]);

  const balances = useMemo(
    () => Object.entries(wallet?.balances ?? {}).sort(([left], [right]) => left.localeCompare(right)),
    [wallet],
  );
  const selectedBalance = currency ? wallet?.balances[currency] ?? 0 : 0;

  async function refreshWallet() {
    const next = await getWallet();
    setWallet(next);
    return next;
  }

  function useFullBalance() {
    if (!currency || selectedBalance <= 0) return;
    setAmount(minorMoneyInputValue(selectedBalance, currency));
  }

  async function payout() {
    if (!currency) {
      setError("Choose a funded wallet currency before requesting a payout.");
      return;
    }

    let amountMinor: number;
    try {
      amountMinor = majorMoneyInputToMinor(amount, currency);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Enter a valid payout amount.");
      return;
    }
    if (amountMinor <= 0) {
      setError("Payout amount must be greater than zero.");
      return;
    }
    if (amountMinor > selectedBalance) {
      setError("Requested amount is above the currently displayed ledger balance.");
      return;
    }

    const exactAmount = formatMinorMoney(amountMinor, currency);
    if (
      !window.confirm(
        `Request a ${exactAmount} payout through the currently configured ${CURRENT_PAYMENT_PROVIDER} provider? The backend will reserve funds, execute the provider payout, and restore the wallet if the provider fails.`,
      )
    ) {
      return;
    }

    if (!payoutKey.current) payoutKey.current = crypto.randomUUID();
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await requestPayout({
        amountMinor,
        currency,
        idempotencyKey: payoutKey.current,
      });
      payoutKey.current = null;
      setLastPayout(result);
      await refreshWallet();
      setAmount("");
      setMessage(
        `Backend confirmed ${formatMinorMoney(result.amount_minor, result.currency)} payout status ${result.status.toLowerCase()}.`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Payout request failed.");
    } finally {
      setBusy(false);
    }
  }

  if (status === "loading") {
    return (
      <main className={styles.walletPage}>
        <section className={styles.walletState} role="status">Checking secure wallet access…</section>
      </main>
    );
  }

  if (status !== "authenticated" || !user) {
    return (
      <main className={styles.walletPage}>
        <section className={styles.walletState}>
          <h1>Sign in to open your wallet.</h1>
          <p>Wallet balances and payouts are private ledger-backed freelancer data.</p>
          <Link href="/login?next=/dashboard/wallet">Sign in securely</Link>
        </section>
      </main>
    );
  }

  if (!isFreelancer) {
    return (
      <main className={styles.walletPage}>
        <section className={styles.walletState}>
          <h1>Freelancer wallet only.</h1>
          <p>Your current role does not expose freelancer wallet or payout controls. The backend still enforces this authorization independently.</p>
          <Link href="/dashboard">Return to dashboard</Link>
        </section>
      </main>
    );
  }

  return (
    <main className={styles.walletPage}>
      <section className={styles.walletHero}>
        <div>
          <Link href="/dashboard">← Dashboard</Link>
          <span>Ledger-backed freelancer money</span>
          <h1>Wallet & payouts</h1>
          <p>
            Every displayed balance comes from immutable ledger entries. This browser never maintains a parallel balance or subtracts a payout optimistically.
          </p>
        </div>
        <aside>
          <span>Configured provider</span>
          <strong>{CURRENT_PAYMENT_PROVIDER}</strong>
          <p>This repository currently configures only the backend sandbox payment provider.</p>
        </aside>
      </section>

      {error ? <p className={styles.walletError} role="alert">{error}</p> : null}
      {message ? <p className={styles.walletSuccess} role="status">{message}</p> : null}

      <section className={styles.walletPanel} aria-labelledby="balances-heading">
        <div className={styles.walletHeading}>
          <div>
            <span>Authoritative ledger view</span>
            <h2 id="balances-heading">Available balances</h2>
          </div>
          <p>
            The current API exposes available wallet balances by currency. It does not expose a separate reserved-balance field, so this UI does not invent one.
          </p>
        </div>

        {!wallet ? (
          <p className={styles.loading} role="status">Loading ledger balances…</p>
        ) : balances.length ? (
          <div className={styles.balanceGrid}>
            {balances.map(([code, amountMinor]) => (
              <article key={code} data-currency={code}>
                <span>{code}</span>
                <strong>{formatMinorMoney(amountMinor, code)}</strong>
                <small>Available from backend ledger</small>
              </article>
            ))}
          </div>
        ) : (
          <div className={styles.emptyWallet}>
            <strong>No available wallet balance yet.</strong>
            <p>Released milestone funds will appear here after the backend posts them to the freelancer wallet ledger.</p>
          </div>
        )}
      </section>

      <section className={styles.walletPanel} aria-labelledby="payout-heading">
        <div className={styles.walletHeading}>
          <div>
            <span>Idempotent money mutation</span>
            <h2 id="payout-heading">Request payout</h2>
          </div>
          <p>
            A confirmation shows the exact amount and currency. Success is rendered only after backend/provider confirmation, then balances are re-read from the ledger.
          </p>
        </div>

        {balances.length ? (
          <div className={styles.payoutForm}>
            <label>
              <span>Currency</span>
              <select
                value={currency}
                disabled={busy}
                onChange={(event) => {
                  setCurrency(event.target.value);
                  setAmount("");
                  setError("");
                }}
              >
                {balances.map(([code]) => <option key={code} value={code}>{code}</option>)}
              </select>
            </label>
            <label>
              <span>Payout amount</span>
              <div className={styles.amountControl}>
                <input
                  inputMode="decimal"
                  autoComplete="off"
                  value={amount}
                  disabled={busy}
                  onChange={(event) => setAmount(event.target.value)}
                  placeholder={currency ? minorMoneyInputValue(selectedBalance, currency) : "0"}
                  aria-describedby="wallet-balance-hint"
                />
                <button type="button" disabled={busy || selectedBalance <= 0} onClick={useFullBalance}>Use full balance</button>
              </div>
              <small id="wallet-balance-hint">
                Displayed available balance: {currency ? formatMinorMoney(selectedBalance, currency) : "—"}. The backend revalidates sufficiency when the request is posted.
              </small>
            </label>
            <button className={styles.payoutButton} type="button" disabled={busy || selectedBalance <= 0} onClick={() => void payout()}>
              {busy ? "Confirming payout…" : "Review payout request"}
            </button>
          </div>
        ) : (
          <p className={styles.authorityNote}>A payout control appears only after the backend returns an available currency balance.</p>
        )}

        {lastPayout ? (
          <dl className={styles.payoutReceipt}>
            <div><dt>Status</dt><dd>{lastPayout.status}</dd></div>
            <div><dt>Amount</dt><dd>{formatMinorMoney(lastPayout.amount_minor, lastPayout.currency)}</dd></div>
            <div><dt>Provider</dt><dd>{lastPayout.provider}</dd></div>
            <div><dt>Reference</dt><dd>{lastPayout.provider_reference ?? "Backend recorded"}</dd></div>
          </dl>
        ) : null}
      </section>
    </main>
  );
}
