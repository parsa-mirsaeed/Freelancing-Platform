"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import {
  canOfferContractCancellation,
  canSignCurrentVersion,
  cancelContract,
  memberRoleForContract,
  milestoneActions,
  signContract,
  transitionMilestone,
  type Contract,
  type Milestone,
  type MilestoneAction,
} from "@/lib/api/contracts";
import { productJson } from "@/lib/api/product-client";
import { formatMinorMoney, formatShortDateTime } from "@/lib/intl";

import styles from "./contracts.module.css";

const ACTION_LABELS: Record<MilestoneAction, string> = {
  start: "Start work",
  submit: "Submit work",
  "request-changes": "Request changes",
  approve: "Approve work",
};

function contractPath(contractId?: string, projectId?: string): string | null {
  if (contractId) return `contracts/${contractId}`;
  if (projectId) return `projects/${projectId}/contract`;
  return null;
}

function replaceMilestone(contract: Contract, milestone: Milestone): Contract {
  return {
    ...contract,
    version: {
      ...contract.version,
      milestones: contract.version.milestones.map((item) =>
        item.id === milestone.id ? milestone : item,
      ),
    },
  };
}

function projectTitle(contract: Contract): string {
  return contract.version.snapshot.scope?.project_title?.trim() || "Contract workspace";
}

function totalPrice(contract: Contract): string {
  const amount = contract.version.snapshot.price?.amount_minor;
  const currency = contract.version.snapshot.currency;
  if (typeof amount !== "number" || !currency) {
    return contract.version.milestones.length
      ? formatMinorMoney(
          contract.version.milestones.reduce((total, item) => total + item.amount_minor, 0),
          contract.version.milestones[0]?.currency ?? "USD",
        )
      : "—";
  }
  return formatMinorMoney(amount, currency);
}

function hashPreview(hash: string): string {
  return `${hash.slice(0, 12)}…${hash.slice(-12)}`;
}

function statusLabel(value: string): string {
  return value.replaceAll("_", " ");
}

export function ContractWorkspace({
  contractId,
  projectId,
}: {
  contractId?: string;
  projectId?: string;
}) {
  const { user, status } = useSession();
  const [contract, setContract] = useState<Contract | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const signingKey = useRef<string | null>(null);

  useEffect(() => {
    if (status !== "authenticated" || !user) return;
    const path = contractPath(contractId, projectId);
    if (!path) return;
    const controller = new AbortController();
    void productJson<Contract>(path, { signal: controller.signal })
      .then((next) => {
        setContract(next);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load contract.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [contractId, projectId, status, user]);

  const role = useMemo(
    () => (contract && user ? memberRoleForContract(contract, user.id) : null),
    [contract, user],
  );

  async function sign() {
    if (!contract || !user || !canSignCurrentVersion(contract, user.id)) return;
    const confirmed = window.confirm(
      `Sign contract version ${contract.current_version}? Your signature will be bound to document hash ${hashPreview(contract.version.document_hash)}.`,
    );
    if (!confirmed) return;
    if (!signingKey.current) signingKey.current = crypto.randomUUID();
    setBusyKey("sign");
    setError("");
    setMessage("");
    try {
      const updated = await signContract(contract, signingKey.current);
      signingKey.current = null;
      setContract(updated);
      setMessage(
        updated.status === "ACTIVE"
          ? "Signature recorded. All required signatures are present and the contract is active."
          : "Signature recorded against the current immutable document. Awaiting the other required party.",
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to sign contract.");
    } finally {
      setBusyKey("");
    }
  }

  async function cancel() {
    if (!contract || !role || !canOfferContractCancellation(contract, role)) return;
    if (
      !window.confirm(
        "Cancel this contract? The backend will reject cancellation if funding is pending or milestone work has started.",
      )
    ) {
      return;
    }
    setBusyKey("cancel");
    setError("");
    setMessage("");
    try {
      const updated = await cancelContract(contract.id);
      setContract(updated);
      setMessage("Contract cancellation confirmed by the backend.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to cancel contract.");
    } finally {
      setBusyKey("");
    }
  }

  async function applyMilestoneAction(milestone: Milestone, action: MilestoneAction) {
    if (!contract || !role) return;
    const note = notes[milestone.id]?.trim() ?? "";
    if (action === "request-changes" && !note) {
      setError("A clear change-request note is required before requesting changes.");
      return;
    }
    const requiresConfirmation = action === "approve";
    if (
      requiresConfirmation &&
      !window.confirm(
        `Approve “${milestone.title}”? Approval is a backend milestone transition and the money release remains a separate employer action in the payment workflow.`,
      )
    ) {
      return;
    }
    setBusyKey(`${milestone.id}:${action}`);
    setError("");
    setMessage("");
    try {
      const updated = await transitionMilestone(milestone.id, action, note);
      setContract(replaceMilestone(contract, updated));
      setNotes((current) => ({ ...current, [milestone.id]: "" }));
      setMessage(
        `Milestone moved to ${statusLabel(updated.status).toLowerCase()} after backend confirmation.`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Milestone transition failed.");
    } finally {
      setBusyKey("");
    }
  }

  if (status === "loading") {
    return (
      <section className={styles.loading} role="status">
        Checking secure session…
      </section>
    );
  }
  if (status !== "authenticated" || !user) {
    const next = contractId
      ? `/dashboard/contracts/${contractId}`
      : `/dashboard/projects/${projectId ?? ""}/contract`;
    return (
      <section className={styles.accessState}>
        <h1>Sign in to open this private contract.</h1>
        <p>Contract snapshots, signatures, and milestone history are visible only to the parties.</p>
        <Link href={`/login?next=${encodeURIComponent(next)}`}>Sign in securely</Link>
      </section>
    );
  }
  if (loading) {
    return (
      <section className={styles.loading} role="status">
        Loading immutable contract…
      </section>
    );
  }
  if (!contract || !role) {
    return (
      <section className={styles.accessState}>
        <h1>Contract unavailable.</h1>
        <p>{error || "This contract is private or no longer available."}</p>
      </section>
    );
  }

  const snapshot = contract.version.snapshot;
  const userSigned = contract.version.signatures.some((item) => item.user_id === user.id);
  const signedIds = new Set(contract.version.signatures.map((item) => item.user_id));
  const requiredParties = contract.parties.filter((party) => party.required_signature);
  const signatureCount = requiredParties.filter((party) => signedIds.has(party.user_id)).length;

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <Link href={`/projects/${contract.project_id}`}>← Project brief</Link>
          <p>Immutable contract · version {contract.current_version}</p>
          <h1>{projectTitle(contract)}</h1>
          <div className={styles.heroMeta}>
            <span>{totalPrice(contract)}</span>
            <span>
              {snapshot.delivery_days
                ? `${snapshot.delivery_days} days`
                : "Delivery per milestones"}
            </span>
            <span>{role === "employer" ? "Employer workspace" : "Freelancer workspace"}</span>
          </div>
        </div>
        <aside className={styles.statusCard}>
          <span>Contract status</span>
          <strong data-status={contract.status}>{statusLabel(contract.status)}</strong>
          <p>
            {contract.status === "PENDING_SIGNATURES"
              ? `${signatureCount} of ${requiredParties.length} required signatures recorded.`
              : contract.status === "ACTIVE"
                ? "Both parties signed this exact document version. Milestone execution is enabled by backend state."
                : "This contract is cancelled. Historical terms and signatures remain visible."}
          </p>
        </aside>
      </section>

      {error ? (
        <p className={styles.errorBanner} role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className={styles.successBanner} role="status">
          {message}
        </p>
      ) : null}

      <section className={styles.documentPanel} aria-labelledby="contract-document-heading">
        <div className={styles.sectionHeading}>
          <div>
            <span>Signed source of truth</span>
            <h2 id="contract-document-heading">Contract snapshot</h2>
          </div>
          <div className={styles.hashBlock}>
            <span>SHA-256 document hash</span>
            <code title={contract.version.document_hash}>
              {hashPreview(contract.version.document_hash)}
            </code>
          </div>
        </div>

        <div className={styles.scopeGrid}>
          <article>
            <span>Project scope</span>
            <h3>{snapshot.scope?.project_title || "Project scope"}</h3>
            <p>
              {snapshot.scope?.project_description ||
                "No additional project description was snapshotted."}
            </p>
          </article>
          <article>
            <span>Accepted proposal</span>
            <h3>Version {snapshot.source?.proposal_version ?? "—"}</h3>
            <p>
              {snapshot.scope?.proposal_cover_letter ||
                "No proposal cover letter was snapshotted."}
            </p>
          </article>
        </div>

        <dl className={styles.documentFacts}>
          <div>
            <dt>Contract value</dt>
            <dd>{totalPrice(contract)}</dd>
          </div>
          <div>
            <dt>Currency</dt>
            <dd>{snapshot.currency || contract.version.milestones[0]?.currency || "—"}</dd>
          </div>
          <div>
            <dt>Delivery</dt>
            <dd>{snapshot.delivery_days ? `${snapshot.delivery_days} days` : "—"}</dd>
          </div>
          <div>
            <dt>Platform commission</dt>
            <dd>
              {typeof snapshot.commission?.platform_bps === "number"
                ? `${snapshot.commission.platform_bps / 100}%`
                : "—"}
            </dd>
          </div>
        </dl>
      </section>

      <section className={styles.signatureSection} aria-labelledby="signature-heading">
        <div className={styles.sectionHeading}>
          <div>
            <span>Hash-bound approval</span>
            <h2 id="signature-heading">Required signatures</h2>
          </div>
          <p>
            Signatures are stored against this backend-generated document hash. The browser never
            computes replacement contract terms.
          </p>
        </div>
        <div className={styles.partyGrid}>
          {contract.parties.map((party) => {
            const signature = contract.version.signatures.find(
              (item) => item.user_id === party.user_id,
            );
            return (
              <article key={party.user_id} className={styles.partyCard}>
                <div>
                  <span>{party.role}</span>
                  <strong>
                    {party.user_id === user.id ? "You" : `Party ${party.user_id.slice(0, 8)}`}
                  </strong>
                </div>
                <p>
                  {signature
                    ? `Signed ${formatShortDateTime(signature.signed_at)}`
                    : party.required_signature
                      ? "Signature required"
                      : "Signature optional"}
                </p>
                <small>
                  {signature ? `Hash ${hashPreview(signature.document_hash)}` : "Not yet signed"}
                </small>
              </article>
            );
          })}
        </div>
        <div className={styles.signatureActions}>
          {canSignCurrentVersion(contract, user.id) ? (
            <button type="button" disabled={Boolean(busyKey)} onClick={() => void sign()}>
              {busyKey === "sign" ? "Recording signature…" : `Sign version ${contract.current_version}`}
            </button>
          ) : userSigned ? (
            <span className={styles.signedNote}>Your signature is recorded for this version.</span>
          ) : null}
          {canOfferContractCancellation(contract, role) ? (
            <button
              className={styles.dangerButton}
              type="button"
              disabled={Boolean(busyKey)}
              onClick={() => void cancel()}
            >
              {busyKey === "cancel" ? "Cancelling…" : "Cancel contract"}
            </button>
          ) : null}
        </div>
      </section>

      <section className={styles.milestoneSection} aria-labelledby="milestone-heading">
        <div className={styles.sectionHeading}>
          <div>
            <span>Execution state machine</span>
            <h2 id="milestone-heading">Milestones</h2>
          </div>
          <p>
            Funding and release are handled separately in the money workflow. This workspace
            controls execution and review only.
          </p>
        </div>
        <div className={styles.milestoneList}>
          {contract.version.milestones.map((milestone) => {
            const actions = milestoneActions(milestone, role, contract.status);
            const noteRequired = actions.includes("request-changes");
            const noteUseful = actions.includes("submit") || noteRequired;
            return (
              <article className={styles.milestoneCard} key={milestone.id}>
                <header>
                  <div>
                    <span>Milestone {String(milestone.sequence).padStart(2, "0")}</span>
                    <h3>{milestone.title}</h3>
                  </div>
                  <div className={styles.milestoneCommercial}>
                    <strong>{formatMinorMoney(milestone.amount_minor, milestone.currency)}</strong>
                    <span>{milestone.delivery_days} days</span>
                  </div>
                </header>
                <div className={styles.milestoneStatusRow}>
                  <strong data-status={milestone.status}>{statusLabel(milestone.status)}</strong>
                  <p>
                    {milestone.status === "CREATED"
                      ? "Awaiting funding before work can start."
                      : milestone.status === "FUNDED"
                        ? "Escrow is fully funded; freelancer may start work."
                        : milestone.status === "APPROVED"
                          ? "Work is approved; financial release remains a separate employer action."
                          : milestone.status === "DISPUTED"
                            ? "Execution is frozen while the dispute workflow is active."
                            : "Current state is controlled by the backend milestone transition table."}
                  </p>
                </div>

                {milestone.events.length ? (
                  <ol className={styles.timeline} aria-label={`${milestone.title} history`}>
                    {[...milestone.events]
                      .sort((a, b) => a.created_at.localeCompare(b.created_at))
                      .map((event) => (
                        <li key={event.id}>
                          <span aria-hidden="true" />
                          <div>
                            <strong>{statusLabel(event.to_status)}</strong>
                            <small>{formatShortDateTime(event.created_at)}</small>
                            {event.note ? <p>{event.note}</p> : null}
                          </div>
                        </li>
                      ))}
                  </ol>
                ) : (
                  <p className={styles.emptyHistory}>
                    No execution transitions have been recorded yet.
                  </p>
                )}

                {noteUseful ? (
                  <label className={styles.noteField}>
                    <span>{noteRequired ? "Change request note" : "Submission note (optional)"}</span>
                    <textarea
                      maxLength={4000}
                      required={noteRequired}
                      value={notes[milestone.id] ?? ""}
                      onChange={(event) =>
                        setNotes((current) => ({ ...current, [milestone.id]: event.target.value }))
                      }
                      placeholder={
                        noteRequired
                          ? "Describe the exact changes required…"
                          : "Summarize what was delivered…"
                      }
                    />
                  </label>
                ) : null}

                {actions.length ? (
                  <div
                    className={styles.milestoneActions}
                    aria-label={`Actions for ${milestone.title}`}
                  >
                    {actions.map((action) => (
                      <button
                        key={action}
                        type="button"
                        data-action={action}
                        disabled={Boolean(busyKey)}
                        onClick={() => void applyMilestoneAction(milestone, action)}
                      >
                        {busyKey === `${milestone.id}:${action}`
                          ? "Confirming…"
                          : ACTION_LABELS[action]}
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>
    </main>
  );
}
