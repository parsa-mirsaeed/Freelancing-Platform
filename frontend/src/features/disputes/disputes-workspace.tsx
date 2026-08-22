"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import type { Contract, Milestone } from "@/lib/api/contracts";
import {
  attachEvidence,
  getDispute,
  getEvidenceDownload,
  listDisputes,
  openDispute,
  requestEvidenceUpload,
  resolveDispute,
  transitionDispute,
  uploadEvidenceObject,
  type DisputeCase,
  type DisputeOutcome,
  type DisputeStatus,
  type FileObject,
} from "@/lib/api/disputes";
import { productJson } from "@/lib/api/product-client";
import {
  formatMinorMoney,
  formatShortDateTime,
  majorMoneyInputToMinor,
} from "@/lib/intl";

import styles from "./disputes.module.css";

const OPENABLE_MILESTONE_STATES = new Set([
  "FUNDED",
  "IN_PROGRESS",
  "SUBMITTED",
  "CHANGES_REQUESTED",
  "APPROVED",
]);
const EVIDENCE_STATES = new Set<DisputeStatus>([
  "OPEN",
  "EVIDENCE_COLLECTION",
  "NEED_MORE_INFO",
]);
const ADMIN_TRANSITIONS: Record<DisputeStatus, DisputeStatus[]> = {
  OPEN: ["EVIDENCE_COLLECTION"],
  EVIDENCE_COLLECTION: ["UNDER_REVIEW"],
  UNDER_REVIEW: ["NEED_MORE_INFO"],
  NEED_MORE_INFO: ["EVIDENCE_COLLECTION", "UNDER_REVIEW"],
  RESOLVED: [],
};
const STATUS_FILTERS: Array<DisputeStatus | "ALL"> = [
  "ALL",
  "OPEN",
  "EVIDENCE_COLLECTION",
  "UNDER_REVIEW",
  "NEED_MORE_INFO",
  "RESOLVED",
];

function statusLabel(value: string): string {
  return value.replaceAll("_", " ");
}

function mergeCase(items: DisputeCase[], dispute: DisputeCase): DisputeCase[] {
  return [dispute, ...items.filter((item) => item.id !== dispute.id)].sort((a, b) =>
    b.created_at.localeCompare(a.created_at),
  );
}

async function resolveContractContext({
  contractId,
  projectId,
  signal,
}: {
  contractId?: string;
  projectId?: string;
  signal: AbortSignal;
}): Promise<Contract | null> {
  if (contractId) return productJson<Contract>(`contracts/${contractId}`, { signal });
  if (projectId) return productJson<Contract>(`projects/${projectId}/contract`, { signal });
  return null;
}

function milestoneForDispute(dispute: DisputeCase, contract: Contract | null): Milestone | null {
  return contract?.version.milestones.find((item) => item.id === dispute.milestone_id) ?? null;
}

export function DisputesWorkspace({
  contractId,
  projectId,
  disputeId,
}: {
  contractId?: string;
  projectId?: string;
  disputeId?: string;
}) {
  const { user, status } = useSession();
  const [items, setItems] = useState<DisputeCase[]>([]);
  const [nextAfter, setNextAfter] = useState<string | null>(null);
  const [selected, setSelected] = useState<DisputeCase | null>(null);
  const [contract, setContract] = useState<Contract | null>(null);
  const [statusFilter, setStatusFilter] = useState<DisputeStatus | "ALL">("ALL");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [openMilestoneId, setOpenMilestoneId] = useState("");
  const [openReason, setOpenReason] = useState("");
  const [evidenceFile, setEvidenceFile] = useState<File | null>(null);
  const [evidenceNote, setEvidenceNote] = useState("");
  const [pendingEvidence, setPendingEvidence] = useState<FileObject | null>(null);
  const [adminReason, setAdminReason] = useState("");
  const [outcome, setOutcome] = useState<DisputeOutcome>("RELEASE_TO_FREELANCER");
  const [freelancerAward, setFreelancerAward] = useState("");
  const [clientRefund, setClientRefund] = useState("");
  const resolutionKey = useRef<string | null>(null);

  useEffect(() => {
    if (status !== "authenticated" || !user) return;
    const controller = new AbortController();

    async function loadWorkspace() {
      try {
        const [page, nextContract] = await Promise.all([
          listDisputes({
            limit: 50,
            status: statusFilter === "ALL" ? undefined : statusFilter,
            signal: controller.signal,
          }),
          resolveContractContext({ contractId, projectId, signal: controller.signal }),
        ]);
        if (controller.signal.aborted) return;

        let nextSelected: DisputeCase | null = null;
        if (disputeId) {
          nextSelected = await getDispute(disputeId, controller.signal);
        } else if (nextContract) {
          nextSelected = page.items.find((item) => item.contract_id === nextContract.id) ?? null;
        } else {
          nextSelected = page.items[0] ?? null;
        }
        if (controller.signal.aborted) return;

        const firstOpenable = nextContract?.version.milestones.find((milestone) =>
          OPENABLE_MILESTONE_STATES.has(milestone.status),
        );
        setItems(page.items);
        setNextAfter(page.next_after);
        setContract(nextContract);
        setSelected(nextSelected);
        setOpenMilestoneId((current) => current || firstOpenable?.id || "");
        setLoading(false);
      } catch (reason) {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load dispute cases.");
        setLoading(false);
      }
    }

    void loadWorkspace();
    return () => controller.abort();
  }, [contractId, disputeId, projectId, status, statusFilter, user]);

  const isAdmin = Boolean(user?.roles.includes("admin"));
  const isParty = Boolean(
    selected && user && selected.parties.some((party) => party.user_id === user.id),
  );
  const selectedMilestone = selected
    ? (selected.milestone ?? milestoneForDispute(selected, contract))
    : null;
  const eligibleMilestones =
    contract?.version.milestones.filter((milestone) =>
      OPENABLE_MILESTONE_STATES.has(milestone.status),
    ) ?? [];

  async function refreshCase(caseId: string) {
    const next = await getDispute(caseId);
    setSelected(next);
    setItems((current) => mergeCase(current, next));
    return next;
  }

  async function createCase() {
    const reason = openReason.trim();
    if (!openMilestoneId) {
      setError("Choose an eligible funded or in-flight milestone first.");
      return;
    }
    if (!reason) {
      setError("Explain why the milestone should be frozen for dispute review.");
      return;
    }
    if (!window.confirm("Open this dispute? The backend will atomically freeze milestone release.")) {
      return;
    }

    setBusy("open");
    setError("");
    setMessage("");
    try {
      const opened = await openDispute(openMilestoneId, reason);
      await refreshCase(opened.id);
      setOpenReason("");
      setMessage("Dispute opened. Milestone release is frozen by backend state.");
    } catch (reasonCaught) {
      setError(reasonCaught instanceof Error ? reasonCaught.message : "Unable to open dispute.");
    } finally {
      setBusy("");
    }
  }

  async function uploadEvidence() {
    if (!selected || !evidenceFile) return;
    setBusy("evidence-upload");
    setError("");
    setMessage("");
    try {
      const reservation = await requestEvidenceUpload(evidenceFile);
      const uploaded = await uploadEvidenceObject(reservation, evidenceFile);
      if (uploaded.status === "SAFE") {
        await attachEvidence(selected.id, uploaded.id, evidenceNote.trim());
        await refreshCase(selected.id);
        setPendingEvidence(null);
        setEvidenceFile(null);
        setEvidenceNote("");
        setMessage("SAFE evidence attached to the immutable dispute record.");
      } else if (uploaded.status === "REJECTED") {
        setPendingEvidence(uploaded);
        setError(uploaded.rejection_reason || "Evidence was rejected by file scanning.");
      } else {
        setPendingEvidence(uploaded);
        setMessage("Evidence uploaded to quarantine. Attach is blocked until the scan reports SAFE.");
      }
    } catch (reasonCaught) {
      setError(reasonCaught instanceof Error ? reasonCaught.message : "Evidence upload failed.");
    } finally {
      setBusy("");
    }
  }

  async function checkPendingEvidence() {
    if (!selected || !pendingEvidence) return;
    setBusy("evidence-check");
    setError("");
    try {
      const safe = await getEvidenceDownload(pendingEvidence.id);
      await attachEvidence(selected.id, safe.file.id, evidenceNote.trim());
      await refreshCase(selected.id);
      setPendingEvidence(null);
      setEvidenceFile(null);
      setEvidenceNote("");
      setMessage("Evidence scan is SAFE and the file is now attached to the case.");
    } catch (reasonCaught) {
      setError(
        reasonCaught instanceof Error
          ? reasonCaught.message
          : "Evidence is not SAFE or attachable yet.",
      );
    } finally {
      setBusy("");
    }
  }

  async function downloadEvidence(fileId: string) {
    setBusy(`download:${fileId}`);
    setError("");
    try {
      const reservation = await getEvidenceDownload(fileId);
      window.open(reservation.download_url, "_blank", "noopener,noreferrer");
    } catch (reasonCaught) {
      setError(reasonCaught instanceof Error ? reasonCaught.message : "Unable to authorize download.");
    } finally {
      setBusy("");
    }
  }

  async function moveCase(toStatus: DisputeStatus) {
    if (!selected) return;
    const reason = adminReason.trim();
    if (!reason) {
      setError("Administrative transitions require a reason for the immutable audit trail.");
      return;
    }

    setBusy(`transition:${toStatus}`);
    setError("");
    setMessage("");
    try {
      await transitionDispute(selected.id, toStatus, reason);
      const next = await refreshCase(selected.id);
      setAdminReason("");
      setMessage(`Case moved to ${statusLabel(next.status).toLowerCase()} after backend confirmation.`);
    } catch (reasonCaught) {
      setError(reasonCaught instanceof Error ? reasonCaught.message : "Dispute transition failed.");
    } finally {
      setBusy("");
    }
  }

  async function decideCase() {
    if (!selected || !selectedMilestone) return;
    const reason = adminReason.trim();
    if (!reason) {
      setError("A final arbitration reason is required for the immutable decision and audit event.");
      return;
    }

    let freelancerAwardMinor: number | undefined;
    let clientRefundMinor: number | undefined;
    if (outcome === "SPLIT") {
      try {
        freelancerAwardMinor = majorMoneyInputToMinor(freelancerAward, selectedMilestone.currency);
        clientRefundMinor = majorMoneyInputToMinor(clientRefund, selectedMilestone.currency);
      } catch (reasonCaught) {
        setError(reasonCaught instanceof Error ? reasonCaught.message : "Enter valid split amounts.");
        return;
      }
      if (freelancerAwardMinor + clientRefundMinor !== selectedMilestone.amount_minor) {
        setError(
          `Split must equal exactly ${formatMinorMoney(
            selectedMilestone.amount_minor,
            selectedMilestone.currency,
          )}.`,
        );
        return;
      }
    }

    if (!resolutionKey.current) resolutionKey.current = crypto.randomUUID();
    const allocation =
      outcome === "RELEASE_TO_FREELANCER"
        ? "release the full funded amount to the freelancer entitlement"
        : outcome === "REFUND_CLIENT"
          ? "refund the full funded amount to the client"
          : `split ${formatMinorMoney(
              freelancerAwardMinor ?? 0,
              selectedMilestone.currency,
            )} to freelancer entitlement and ${formatMinorMoney(
              clientRefundMinor ?? 0,
              selectedMilestone.currency,
            )} to the client`;
    if (
      !window.confirm(
        `Resolve this dispute and ${allocation}? This is a terminal idempotent ledger operation and cannot be decided twice.`,
      )
    ) {
      return;
    }

    setBusy("resolve");
    setError("");
    setMessage("");
    try {
      await resolveDispute({
        disputeId: selected.id,
        outcome,
        reason,
        freelancerAwardMinor,
        clientRefundMinor,
        idempotencyKey: resolutionKey.current,
      });
      resolutionKey.current = null;
      const next = await refreshCase(selected.id);
      setAdminReason("");
      setMessage(
        `Dispute resolved as ${statusLabel(next.decision?.outcome ?? outcome).toLowerCase()}.`,
      );
    } catch (reasonCaught) {
      setError(reasonCaught instanceof Error ? reasonCaught.message : "Dispute resolution failed.");
    } finally {
      setBusy("");
    }
  }

  async function loadOlder() {
    if (!nextAfter) return;
    setBusy("older");
    setError("");
    try {
      const page = await listDisputes({
        after: nextAfter,
        limit: 50,
        status: statusFilter === "ALL" ? undefined : statusFilter,
      });
      setItems((current) => {
        const seen = new Set(current.map((item) => item.id));
        return [...current, ...page.items.filter((item) => !seen.has(item.id))];
      });
      setNextAfter(page.next_after);
    } catch (reasonCaught) {
      setError(reasonCaught instanceof Error ? reasonCaught.message : "Unable to load older cases.");
    } finally {
      setBusy("");
    }
  }

  if (status === "loading") {
    return (
      <main className={styles.statePage} role="status">
        Checking secure session…
      </main>
    );
  }
  if (status !== "authenticated" || !user) {
    return (
      <main className={styles.statePage}>
        <h1>Sign in to review disputes.</h1>
        <p>Cases are visible only to their contract parties and authorized administrators.</p>
        <Link href="/login?next=/dashboard/disputes">Sign in securely</Link>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div>
          <Link href="/dashboard">← Dashboard</Link>
          <p>Evidence · freeze · arbitration · audit</p>
          <h1>Dispute resolution</h1>
          <span>
            {isAdmin
              ? "Administrator queue. Every transition and decision is backend-audited."
              : "Your contract disputes. Opening a case freezes release before evidence review."}
          </span>
        </div>
        <aside>
          <small>Control boundary</small>
          <strong>Ledger + state machine</strong>
          <p>The browser never decides financial truth. Backend state and the balanced ledger do.</p>
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

      {contract ? (
        <section className={styles.openPanel} aria-labelledby="open-dispute-heading">
          <div>
            <span>Contract {contract.id.slice(0, 8)}</span>
            <h2 id="open-dispute-heading">Open or review a milestone dispute</h2>
            <p>
              Only funded or in-flight milestones are eligible. Existing disputed milestones remain
              frozen until an administrator records a terminal decision.
            </p>
          </div>
          <div className={styles.openControls}>
            <label>
              <span>Milestone</span>
              <select
                aria-label="Milestone"
                value={openMilestoneId}
                onChange={(event) => setOpenMilestoneId(event.target.value)}
              >
                <option value="">Choose milestone</option>
                {eligibleMilestones.map((milestone) => (
                  <option key={milestone.id} value={milestone.id}>
                    {milestone.sequence}. {milestone.title} · {statusLabel(milestone.status)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Reason for dispute</span>
              <textarea
                aria-label="Reason for dispute"
                maxLength={4000}
                value={openReason}
                onChange={(event) => setOpenReason(event.target.value)}
                placeholder="Describe the material scope, delivery, or acceptance issue…"
              />
            </label>
            <button
              type="button"
              disabled={Boolean(busy) || !eligibleMilestones.length}
              onClick={() => void createCase()}
            >
              {busy === "open" ? "Freezing milestone…" : "Open dispute and freeze release"}
            </button>
            {contract.version.milestones.some((milestone) => milestone.status === "DISPUTED") ? (
              <p className={styles.frozenNote}>
                A milestone in this contract is already frozen as DISPUTED. Select its case from the
                inbox below.
              </p>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className={styles.workspace}>
        <aside className={styles.inbox} aria-label="Dispute inbox">
          <div className={styles.inboxHeader}>
            <div>
              <span>{isAdmin ? "Arbitration queue" : "Your cases"}</span>
              <h2>Disputes</h2>
            </div>
            <select
              aria-label="Filter dispute status"
              value={statusFilter}
              onChange={(event) => {
                setLoading(true);
                setStatusFilter(event.target.value as DisputeStatus | "ALL");
              }}
            >
              {STATUS_FILTERS.map((filter) => (
                <option key={filter} value={filter}>
                  {statusLabel(filter)}
                </option>
              ))}
            </select>
          </div>
          {loading ? <p role="status">Loading authorized cases…</p> : null}
          {!loading && !items.length ? (
            <p className={styles.empty}>No visible disputes match this filter.</p>
          ) : null}
          <div className={styles.caseList}>
            {items.map((item) => (
              <button
                type="button"
                key={item.id}
                className={selected?.id === item.id ? styles.activeCase : undefined}
                onClick={() => void refreshCase(item.id)}
              >
                <span>{item.milestone?.title ?? `Milestone ${item.milestone_id.slice(0, 8)}`}</span>
                <strong data-status={item.status}>{statusLabel(item.status)}</strong>
                <small>{formatShortDateTime(item.created_at)}</small>
                <p>{item.reason}</p>
              </button>
            ))}
          </div>
          {nextAfter ? (
            <button
              className={styles.loadMore}
              type="button"
              disabled={Boolean(busy)}
              onClick={() => void loadOlder()}
            >
              {busy === "older" ? "Loading…" : "Load older cases"}
            </button>
          ) : null}
        </aside>

        <section className={styles.caseDetail} aria-label="Dispute case detail">
          {!selected ? (
            <div className={styles.emptyDetail}>
              <h2>Select a dispute</h2>
              <p>Evidence, state transitions, and final ledger allocation will appear here.</p>
            </div>
          ) : (
            <>
              <header className={styles.caseHeader}>
                <div>
                  <span>Case {selected.id.slice(0, 8)}</span>
                  <h2>{selectedMilestone?.title ?? "Milestone dispute"}</h2>
                  <p>{selected.reason}</p>
                </div>
                <strong data-status={selected.status}>{statusLabel(selected.status)}</strong>
              </header>

              <dl className={styles.caseFacts}>
                <div>
                  <dt>Opened</dt>
                  <dd>{formatShortDateTime(selected.created_at)}</dd>
                </div>
                <div>
                  <dt>Milestone</dt>
                  <dd>
                    {selectedMilestone
                      ? formatMinorMoney(selectedMilestone.amount_minor, selectedMilestone.currency)
                      : selected.milestone_id.slice(0, 8)}
                  </dd>
                </div>
                <div>
                  <dt>Evidence</dt>
                  <dd>{selected.evidence.length} files</dd>
                </div>
                <div>
                  <dt>Parties</dt>
                  <dd>{selected.parties.length}</dd>
                </div>
              </dl>

              <section className={styles.timelinePanel} aria-labelledby="case-timeline-heading">
                <div className={styles.sectionTitle}>
                  <span>Immutable history</span>
                  <h3 id="case-timeline-heading">Case timeline</h3>
                </div>
                <ol>
                  {selected.events.map((event, index) => (
                    <li key={`${event.event_type}-${event.created_at}-${index}`}>
                      <span aria-hidden="true" />
                      <div>
                        <strong>{statusLabel(event.event_type)}</strong>
                        <small>{formatShortDateTime(event.created_at)}</small>
                        <p>{event.reason}</p>
                        {event.to_status ? <em>{statusLabel(event.to_status)}</em> : null}
                      </div>
                    </li>
                  ))}
                </ol>
              </section>

              <section className={styles.evidencePanel} aria-labelledby="evidence-heading">
                <div className={styles.sectionTitle}>
                  <span>SAFE files only</span>
                  <h3 id="evidence-heading">Evidence</h3>
                </div>
                {selected.evidence.length ? (
                  <div className={styles.evidenceList}>
                    {selected.evidence.map((evidence) => (
                      <article key={evidence.id}>
                        <div>
                          <strong>Evidence {evidence.id.slice(0, 8)}</strong>
                          <span>{evidence.note || "No note supplied"}</span>
                          <small>{formatShortDateTime(evidence.created_at)}</small>
                        </div>
                        <button
                          type="button"
                          disabled={Boolean(busy)}
                          onClick={() => void downloadEvidence(evidence.file_id)}
                        >
                          {busy === `download:${evidence.file_id}` ? "Authorizing…" : "Open evidence"}
                        </button>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className={styles.empty}>No evidence has been attached.</p>
                )}

                {isParty && EVIDENCE_STATES.has(selected.status) ? (
                  <div className={styles.evidenceComposer}>
                    <label>
                      <span>Evidence file</span>
                      <input
                        aria-label="Evidence file"
                        type="file"
                        onChange={(event) => setEvidenceFile(event.target.files?.[0] ?? null)}
                      />
                    </label>
                    <label>
                      <span>Evidence note</span>
                      <textarea
                        aria-label="Evidence note"
                        maxLength={4000}
                        value={evidenceNote}
                        onChange={(event) => setEvidenceNote(event.target.value)}
                        placeholder="Explain what this file establishes…"
                      />
                    </label>
                    <button
                      type="button"
                      disabled={Boolean(busy) || !evidenceFile}
                      onClick={() => void uploadEvidence()}
                    >
                      {busy === "evidence-upload" ? "Uploading to quarantine…" : "Upload evidence"}
                    </button>
                    {pendingEvidence && pendingEvidence.status !== "SAFE" ? (
                      <div className={styles.scanState}>
                        <strong data-status={pendingEvidence.status}>
                          {statusLabel(pendingEvidence.status)}
                        </strong>
                        <span>Attachment remains blocked until SAFE.</span>
                        <button
                          type="button"
                          disabled={Boolean(busy)}
                          onClick={() => void checkPendingEvidence()}
                        >
                          {busy === "evidence-check" ? "Checking…" : "Check scan and attach"}
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </section>

              {selected.decision ? (
                <section className={styles.decisionPanel} aria-labelledby="decision-heading">
                  <div className={styles.sectionTitle}>
                    <span>Terminal ledger allocation</span>
                    <h3 id="decision-heading">Final decision</h3>
                  </div>
                  <strong>{statusLabel(selected.decision.outcome)}</strong>
                  <p>{selected.decision.reason}</p>
                  <dl>
                    <div>
                      <dt>Freelancer award</dt>
                      <dd>
                        {formatMinorMoney(
                          selected.decision.freelancer_award_minor,
                          selected.decision.currency,
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>Freelancer net</dt>
                      <dd>
                        {formatMinorMoney(
                          selected.decision.freelancer_net_minor,
                          selected.decision.currency,
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>Client refund</dt>
                      <dd>
                        {formatMinorMoney(
                          selected.decision.client_refund_minor,
                          selected.decision.currency,
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>Platform commission</dt>
                      <dd>
                        {formatMinorMoney(
                          selected.decision.commission_minor,
                          selected.decision.currency,
                        )}
                      </dd>
                    </div>
                  </dl>
                  <small>Journal {selected.decision.journal_transaction_id}</small>
                </section>
              ) : null}

              {isAdmin && selected.status !== "RESOLVED" ? (
                <section className={styles.adminPanel} aria-labelledby="arbitration-heading">
                  <div className={styles.sectionTitle}>
                    <span>Administrator only</span>
                    <h3 id="arbitration-heading">Arbitration controls</h3>
                  </div>
                  <label>
                    <span>Audit reason</span>
                    <textarea
                      aria-label="Audit reason"
                      maxLength={4000}
                      value={adminReason}
                      onChange={(event) => setAdminReason(event.target.value)}
                      placeholder="Record why this state change or decision is warranted…"
                    />
                  </label>
                  {ADMIN_TRANSITIONS[selected.status].length ? (
                    <div className={styles.transitionActions}>
                      {ADMIN_TRANSITIONS[selected.status].map((nextStatus) => (
                        <button
                          type="button"
                          key={nextStatus}
                          disabled={Boolean(busy)}
                          onClick={() => void moveCase(nextStatus)}
                        >
                          {busy === `transition:${nextStatus}`
                            ? "Recording…"
                            : `Move to ${statusLabel(nextStatus)}`}
                        </button>
                      ))}
                    </div>
                  ) : null}

                  {selected.status === "UNDER_REVIEW" ? (
                    <div className={styles.resolvePanel}>
                      <label>
                        <span>Outcome</span>
                        <select
                          aria-label="Outcome"
                          value={outcome}
                          onChange={(event) => setOutcome(event.target.value as DisputeOutcome)}
                        >
                          <option value="RELEASE_TO_FREELANCER">Release to freelancer</option>
                          <option value="REFUND_CLIENT">Refund client</option>
                          <option value="SPLIT">Split funded amount</option>
                        </select>
                      </label>
                      {outcome === "SPLIT" && selectedMilestone ? (
                        <div className={styles.splitGrid}>
                          <p>
                            Exact funded target:{" "}
                            <strong>
                              {formatMinorMoney(
                                selectedMilestone.amount_minor,
                                selectedMilestone.currency,
                              )}
                            </strong>
                          </p>
                          <label>
                            <span>Freelancer award ({selectedMilestone.currency})</span>
                            <input
                              aria-label={`Freelancer award (${selectedMilestone.currency})`}
                              inputMode="decimal"
                              value={freelancerAward}
                              onChange={(event) => setFreelancerAward(event.target.value)}
                              placeholder="0.00"
                            />
                          </label>
                          <label>
                            <span>Client refund ({selectedMilestone.currency})</span>
                            <input
                              aria-label={`Client refund (${selectedMilestone.currency})`}
                              inputMode="decimal"
                              value={clientRefund}
                              onChange={(event) => setClientRefund(event.target.value)}
                              placeholder="0.00"
                            />
                          </label>
                        </div>
                      ) : null}
                      <button
                        className={styles.resolveButton}
                        type="button"
                        disabled={Boolean(busy) || !selectedMilestone}
                        onClick={() => void decideCase()}
                      >
                        {busy === "resolve" ? "Committing decision…" : "Resolve dispute"}
                      </button>
                    </div>
                  ) : null}
                </section>
              ) : null}
            </>
          )}
        </section>
      </section>
    </main>
  );
}
