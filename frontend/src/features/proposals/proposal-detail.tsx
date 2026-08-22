"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { productJson } from "@/lib/api/product-client";
import {
  canAppendProposalVersion,
  currentProposalVersion,
  proposalActions,
  type Proposal,
  type ProposalAction,
  type ProposalActor,
  type ProposalWritePayload,
} from "@/lib/api/proposals";
import type { Project } from "@/lib/api/work";
import { formatMinorMoney, minorMoneyInputValue } from "@/lib/intl";

import { ProposalEditor } from "./proposal-editor";
import styles from "./proposals.module.css";

const ACTION_LABELS: Record<ProposalAction, string> = {
  submit: "Submit to employer",
  negotiate: "Request negotiation",
  withdraw: "Withdraw proposal",
  reject: "Reject proposal",
  accept: "Accept & create contract",
};

function shouldConfirm(action: ProposalAction): boolean {
  return action === "accept" || action === "reject" || action === "withdraw";
}

function confirmation(action: ProposalAction): string {
  if (action === "accept") {
    return "Accept this proposal? The backend will create the immutable contract snapshot in the same transaction.";
  }
  if (action === "reject") return "Reject this proposal? Rejected is a terminal proposal state.";
  return "Withdraw this proposal? Withdrawn is a terminal proposal state.";
}

export function ProposalDetail({ proposalId }: { proposalId: string }) {
  const { user, status } = useSession();
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (status !== "authenticated" || !user) return;
    const controller = new AbortController();
    void productJson<Proposal>(`proposals/${proposalId}`, { signal: controller.signal })
      .then(async (value) => {
        const projectValue = await productJson<Project>(`projects/${value.project_id}`, {
          signal: controller.signal,
        });
        setProposal(value);
        setProject(projectValue);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load proposal.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [proposalId, status, user]);

  const actor: ProposalActor | null = useMemo(() => {
    if (!proposal || !user) return null;
    if (proposal.freelancer_user_id === user.id && user.roles.includes("freelancer")) return "freelancer";
    if (user.roles.includes("employer")) return "employer";
    return null;
  }, [proposal, user]);

  async function transition(action: ProposalAction) {
    if (!proposal || !actor) return;
    if (shouldConfirm(action) && !window.confirm(confirmation(action))) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const updated = await productJson<Proposal>(`proposals/${proposal.id}/${action}`, {
        method: "POST",
      });
      setProposal(updated);
      setMessage(
        action === "accept"
          ? "Proposal accepted. The backend created the contract snapshot atomically."
          : `Proposal moved to ${updated.status.replaceAll("_", " ").toLowerCase()}.`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Proposal transition failed.");
    } finally {
      setBusy(false);
    }
  }

  async function appendVersion(payload: ProposalWritePayload) {
    if (!proposal) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const updated = await productJson<Proposal>(`proposals/${proposal.id}/versions`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setProposal(updated);
      setMessage(`Version ${updated.current_version} appended. Earlier terms remain immutable.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to append proposal version.");
    } finally {
      setBusy(false);
    }
  }

  if (status === "loading") return <section className={styles.loading} role="status">Checking session…</section>;
  if (status !== "authenticated" || !user) {
    return <section className={styles.accessState}><h1>Sign in to open this private proposal.</h1><Link href={`/login?next=/dashboard/proposals/${proposalId}`}>Sign in</Link></section>;
  }
  if (loading) return <section className={styles.loading} role="status">Loading proposal history…</section>;
  if (!proposal || !project || !actor) {
    return <section className={styles.accessState}><h1>Proposal unavailable.</h1><p>{error || "This proposal is private or no longer available."}</p></section>;
  }

  const current = currentProposalVersion(proposal);
  const actions = proposalActions(proposal.status, actor);
  const revisionInitial = {
    amount: minorMoneyInputValue(current.amount_minor, current.currency),
    currency: current.currency,
    deliveryDays: String(current.delivery_days),
    coverLetter: current.cover_letter,
    milestones: current.milestones.map((item) => ({
      title: item.title,
      amount: minorMoneyInputValue(item.amount_minor, current.currency),
      deliveryDays: String(item.delivery_days),
    })),
  };

  return (
    <main className={styles.detailPage}>
      <section className={styles.detailHero}>
        <div>
          <Link href={actor === "employer" ? `/dashboard/projects/${project.id}/proposals` : `/projects/${project.id}`}>
            ← {actor === "employer" ? "Proposal comparison" : "Project brief"}
          </Link>
          <p>{actor === "freelancer" ? "Your private proposal" : "Employer review"}</p>
          <h1>{project.title}</h1>
          <span>Proposal {proposal.id.slice(0, 8)} · version {proposal.current_version}</span>
        </div>
        <aside className={styles.statusPanel}>
          <span>Proposal status</span>
          <strong data-status={proposal.status}>{proposal.status.replaceAll("_", " ")}</strong>
          <p>
            {proposal.status === "ACCEPTED"
              ? "Accepted is terminal; contract terms now come from the backend snapshot."
              : "State changes are confirmed by the backend proposal state machine."}
          </p>
        </aside>
      </section>

      {error ? <p className={styles.errorBanner} role="alert">{error}</p> : null}
      {message ? <p className={styles.successBanner} role="status">{message}</p> : null}

      <section className={styles.currentTerms}>
        <div className={styles.sectionHeading}>
          <div><span>Current terms</span><h2>Version {current.version_number}</h2></div>
          <strong>{formatMinorMoney(current.amount_minor, current.currency)}</strong>
        </div>
        <div className={styles.termGrid}>
          <div><span>Delivery</span><strong>{current.delivery_days} days</strong></div>
          <div><span>Milestones</span><strong>{current.milestones.length || "None"}</strong></div>
          <div><span>Currency</span><strong>{current.currency}</strong></div>
        </div>
        <div className={styles.letterBlock}>
          <span>Cover letter</span>
          <p>{current.cover_letter || "No cover letter was included in this version."}</p>
        </div>
        {current.milestones.length ? (
          <ol className={styles.termMilestones}>
            {current.milestones.map((item) => (
              <li key={item.id}>
                <span>{String(item.sequence).padStart(2, "0")}</span>
                <div><strong>{item.title}</strong><small>{item.delivery_days} days</small></div>
                <b>{formatMinorMoney(item.amount_minor, current.currency)}</b>
              </li>
            ))}
          </ol>
        ) : null}
      </section>

      {actions.length ? (
        <section className={styles.actionBar} aria-label="Allowed proposal actions">
          <div><span>Available now</span><p>These controls mirror the current backend-valid transitions for your role.</p></div>
          <div>
            {actions.map((action) => (
              <button
                key={action}
                type="button"
                disabled={busy}
                data-action={action}
                onClick={() => void transition(action)}
              >
                {ACTION_LABELS[action]}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <section className={styles.historySection}>
        <div className={styles.sectionHeading}><div><span>Immutable history</span><h2>Commercial versions</h2></div><small>{proposal.versions.length} recorded</small></div>
        <div className={styles.versionHistory}>
          {[...proposal.versions].sort((a, b) => b.version_number - a.version_number).map((version) => (
            <article key={version.id} className={version.version_number === proposal.current_version ? styles.currentVersion : undefined}>
              <div><span>Version {version.version_number}</span><strong>{formatMinorMoney(version.amount_minor, version.currency)}</strong></div>
              <dl>
                <div><dt>Delivery</dt><dd>{version.delivery_days} days</dd></div>
                <div><dt>Milestones</dt><dd>{version.milestones.length}</dd></div>
              </dl>
              <p>{version.cover_letter || "No cover letter."}</p>
            </article>
          ))}
        </div>
      </section>

      {canAppendProposalVersion(proposal.status, actor) ? (
        <section className={styles.revisionSection}>
          <div className={styles.sectionHeading}>
            <div><span>Append-only revision</span><h2>Create version {proposal.current_version + 1}</h2></div>
            <p>Prefilled from the current version for convenience; saving creates a new record rather than overwriting history.</p>
          </div>
          <ProposalEditor
            key={`proposal-version-${proposal.current_version}`}
            projectCurrency={project.currency}
            initial={revisionInitial}
            submitLabel={`Append version ${proposal.current_version + 1}`}
            busy={busy}
            onSubmit={appendVersion}
          />
        </section>
      ) : null}
    </main>
  );
}
