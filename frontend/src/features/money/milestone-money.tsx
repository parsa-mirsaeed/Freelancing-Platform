"use client";

import { useEffect, useRef, useState } from "react";

import type { ContractStatus, MemberRole, Milestone } from "@/lib/api/contracts";
import {
  canOfferFinancialAction,
  financialActionAmount,
  getMilestoneFinancials,
  mutateMilestoneFinancials,
  type FinancialAction,
  type FinancialMutationResult,
  type MilestoneFinancialState,
  type PaymentIntentResult,
} from "@/lib/api/money";
import { formatMinorMoney } from "@/lib/intl";

import styles from "./money.module.css";

function statusLabel(value: string): string {
  return value.replaceAll("_", " ");
}

function isPaymentIntent(value: FinancialMutationResult): value is PaymentIntentResult {
  return "payment_intent_id" in value;
}

function escrowLabel(financial: MilestoneFinancialState, pendingFunding: boolean): string {
  if (pendingFunding) return "AWAITING CAPTURE";
  if (
    financial.escrow_balance_minor === financial.contracted_amount_minor &&
    financial.escrow_balance_minor > 0
  ) {
    return "FULLY FUNDED";
  }
  if (financial.escrow_balance_minor === 0) return "EMPTY";
  return "PARTIALLY FUNDED";
}

function actionLabel(action: FinancialAction): string {
  if (action === "fund") return "Fund escrow";
  if (action === "release") return "Release payment";
  return "Refund escrow";
}

function confirmationCopy(action: FinancialAction, amount: string, title: string): string {
  if (action === "fund") {
    return `Fund ${amount} for “${title}”? The backend will create an idempotent payment request. Escrow is not treated as funded until provider capture is confirmed.`;
  }
  if (action === "release") {
    return `Release ${amount} for “${title}”? The backend will atomically move fully funded escrow to the freelancer wallet and platform commission ledger accounts.`;
  }
  return `Refund the full ${amount} escrow for “${title}”? Refund is available only before work starts and the backend will return the milestone to created after provider confirmation.`;
}

export function MilestoneMoney({
  milestone,
  role,
  contractStatus,
  onAuthoritativeMutation,
}: {
  milestone: Milestone;
  role: MemberRole;
  contractStatus: ContractStatus;
  onAuthoritativeMutation: () => Promise<void>;
}) {
  const [financial, setFinancial] = useState<MilestoneFinancialState | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingFunding, setPendingFunding] = useState(false);
  const [busyAction, setBusyAction] = useState<FinancialAction | "refresh" | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const idempotencyKeys = useRef<Partial<Record<FinancialAction, string>>>({});

  useEffect(() => {
    const controller = new AbortController();
    void getMilestoneFinancials(milestone.id, controller.signal)
      .then((next) => {
        setFinancial(next);
        if (next.milestone_status !== "CREATED" || next.escrow_balance_minor > 0) {
          setPendingFunding(false);
        }
        setError("");
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load milestone finances.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [milestone.id, milestone.status]);

  async function refreshFinancials() {
    const next = await getMilestoneFinancials(milestone.id);
    setFinancial(next);
    if (next.milestone_status !== "CREATED" || next.escrow_balance_minor > 0) {
      setPendingFunding(false);
    }
    return next;
  }

  async function manuallyRefresh() {
    setBusyAction("refresh");
    setError("");
    setMessage("");
    try {
      await Promise.all([refreshFinancials(), onAuthoritativeMutation()]);
      setMessage("Financial and milestone state refreshed from the backend.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to refresh financial state.");
    } finally {
      setBusyAction(null);
    }
  }

  async function runAction(action: FinancialAction) {
    if (
      !financial ||
      (action === "fund" && pendingFunding) ||
      !canOfferFinancialAction({
        action,
        role,
        contractStatus,
        milestoneStatus: milestone.status,
        financial,
      })
    ) {
      return;
    }

    const amountMinor = financialActionAmount(action, financial);
    const amount = formatMinorMoney(amountMinor, financial.currency);
    if (!window.confirm(confirmationCopy(action, amount, milestone.title))) return;

    if (!idempotencyKeys.current[action]) {
      idempotencyKeys.current[action] = crypto.randomUUID();
    }
    const idempotencyKey = idempotencyKeys.current[action];
    if (!idempotencyKey) return;

    setBusyAction(action);
    setError("");
    setMessage("");
    try {
      const result = await mutateMilestoneFinancials(milestone.id, action, idempotencyKey);
      idempotencyKeys.current[action] = undefined;
      if (action === "fund" && isPaymentIntent(result) && result.status === "PENDING") {
        setPendingFunding(true);
      }
      await Promise.all([refreshFinancials(), onAuthoritativeMutation()]);
      if (action === "fund") {
        setMessage(
          isPaymentIntent(result) && result.status === "CAPTURED"
            ? `Backend confirmed ${amount} in funded escrow.`
            : `Funding request accepted for ${amount}. Escrow remains pending until provider capture is confirmed.`,
        );
      } else if (action === "release") {
        setMessage(`Backend confirmed release of ${amount}.`);
      } else {
        setMessage(`Backend confirmed the full ${amount} pre-work refund.`);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${actionLabel(action)} failed.`);
    } finally {
      setBusyAction(null);
    }
  }

  if (loading) {
    return (
      <section className={styles.milestoneFinance} aria-label={`${milestone.title} finances`}>
        <p className={styles.loading} role="status">
          Reading ledger-derived escrow state…
        </p>
      </section>
    );
  }

  if (!financial) {
    return (
      <section className={styles.milestoneFinance} aria-label={`${milestone.title} finances`}>
        <p className={styles.inlineError}>{error || "Financial state is unavailable."}</p>
        <button type="button" onClick={() => void manuallyRefresh()}>
          Retry financial state
        </button>
      </section>
    );
  }

  const actions = (["fund", "release", "refund"] as const).filter(
    (action) =>
      !(action === "fund" && pendingFunding) &&
      canOfferFinancialAction({
        action,
        role,
        contractStatus,
        milestoneStatus: milestone.status,
        financial,
      }),
  );

  return (
    <section className={styles.milestoneFinance} aria-label={`${milestone.title} finances`}>
      <div className={styles.financeHeading}>
        <div>
          <span>Ledger-derived escrow</span>
          <strong>{escrowLabel(financial, pendingFunding)}</strong>
        </div>
        <p>
          Backend milestone {statusLabel(financial.milestone_status).toLowerCase()} · escrow balance{" "}
          {formatMinorMoney(financial.escrow_balance_minor, financial.currency)}
        </p>
      </div>

      <dl className={styles.financeFacts}>
        <div>
          <dt>Contracted</dt>
          <dd>{formatMinorMoney(financial.contracted_amount_minor, financial.currency)}</dd>
        </div>
        <div>
          <dt>Escrow balance</dt>
          <dd>{formatMinorMoney(financial.escrow_balance_minor, financial.currency)}</dd>
        </div>
        <div>
          <dt>Commission</dt>
          <dd>
            {typeof financial.commission_bps === "number"
              ? `${financial.commission_bps / 100}%`
              : "Set when escrow is created"}
          </dd>
        </div>
        <div>
          <dt>Backend milestone</dt>
          <dd>{statusLabel(financial.milestone_status)}</dd>
        </div>
      </dl>

      {error ? (
        <p className={styles.inlineError} role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className={styles.inlineSuccess} role="status">
          {message}
        </p>
      ) : null}

      <div className={styles.moneyActions} aria-label={`Money actions for ${milestone.title}`}>
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            data-money-action={action}
            disabled={busyAction !== null}
            onClick={() => void runAction(action)}
          >
            {busyAction === action ? "Confirming with backend…" : actionLabel(action)}
          </button>
        ))}
        <button
          type="button"
          data-money-action="refresh"
          disabled={busyAction !== null}
          onClick={() => void manuallyRefresh()}
        >
          {busyAction === "refresh" ? "Refreshing…" : "Refresh financial state"}
        </button>
      </div>

      {!actions.length ? (
        <p className={styles.authorityNote}>
          No financial mutation is available for this role and backend-aligned milestone state.
        </p>
      ) : null}
    </section>
  );
}
