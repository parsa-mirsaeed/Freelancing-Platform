"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { productJson } from "@/lib/api/product-client";
import {
  currentProposalVersion,
  proposalActions,
  type Proposal,
  type ProposalAction,
} from "@/lib/api/proposals";
import type { Project } from "@/lib/api/work";
import { formatMinorMoney } from "@/lib/intl";

import styles from "./proposals.module.css";

const EMPLOYER_LABELS: Partial<Record<ProposalAction, string>> = {
  negotiate: "Negotiate",
  reject: "Reject",
  accept: "Accept",
};

export function ProposalCompare({ projectId }: { projectId: string }) {
  const { user, status } = useSession();
  const [project, setProject] = useState<Project | null>(null);
  const [items, setItems] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (status !== "authenticated" || !user?.roles.includes("employer")) return;
    const controller = new AbortController();
    void Promise.all([
      productJson<Project>(`projects/${projectId}`, { signal: controller.signal }),
      productJson<{ items: Proposal[] }>(`projects/${projectId}/proposals`, {
        signal: controller.signal,
      }),
    ])
      .then(([projectValue, proposals]) => {
        setProject(projectValue);
        setItems(proposals.items);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load proposals.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [projectId, status, user]);

  const comparable = useMemo(
    () => items.map((proposal) => ({ proposal, version: currentProposalVersion(proposal) })),
    [items],
  );

  async function transition(proposal: Proposal, action: ProposalAction) {
    if (action === "accept") {
      const confirmed = window.confirm(
        "Accept this proposal? The backend will atomically create the contract snapshot and only one proposal can be accepted for the project.",
      );
      if (!confirmed) return;
    }
    if (action === "reject" && !window.confirm("Reject this proposal? Rejected is terminal.")) return;

    setBusyId(proposal.id);
    setError("");
    setMessage("");
    try {
      const updated = await productJson<Proposal>(`proposals/${proposal.id}/${action}`, {
        method: "POST",
      });
      setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setMessage(
        action === "accept"
          ? "Proposal accepted and contract snapshot created by the backend."
          : `Proposal moved to ${updated.status.replaceAll("_", " ").toLowerCase()}.`,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Proposal transition failed.");
    } finally {
      setBusyId(null);
    }
  }

  if (status === "loading") return <section className={styles.loading} role="status">Checking session…</section>;
  if (status !== "authenticated" || !user) {
    return <section className={styles.accessState}><h1>Sign in to compare project proposals.</h1><Link href={`/login?next=/dashboard/projects/${projectId}/proposals`}>Sign in</Link></section>;
  }
  if (!user.roles.includes("employer")) {
    return <section className={styles.accessState}><h1>Employer account required.</h1><p>Proposal comparison is restricted to the project owner by the backend.</p></section>;
  }
  if (loading) return <section className={styles.loading} role="status">Loading proposal comparison…</section>;
  if (!project) return <section className={styles.accessState}><h1>Project unavailable.</h1><p>{error}</p></section>;

  return (
    <main className={styles.comparePage}>
      <section className={styles.compareHero}>
        <div>
          <Link href="/dashboard/projects">← Employer projects</Link>
          <p>Private commercial comparison</p>
          <h1>{project.title}</h1>
          <span>
            Compare only the current version for each proposal, then open its immutable history before
            making a terminal decision.
          </span>
        </div>
        <aside><strong>{items.length}</strong><span>{items.length === 1 ? "proposal" : "proposals"}</span></aside>
      </section>

      {error ? <p className={styles.errorBanner} role="alert">{error}</p> : null}
      {message ? <p className={styles.successBanner} role="status">{message}</p> : null}

      {comparable.length ? (
        <section className={styles.compareGrid} aria-label="Project proposal comparison">
          {comparable.map(({ proposal, version }, index) => {
            const actions = proposalActions(proposal.status, "employer");
            return (
              <article className={styles.compareCard} key={proposal.id}>
                <div className={styles.compareIndex}>{String(index + 1).padStart(2, "0")}</div>
                <div className={styles.compareStatus} data-status={proposal.status}>
                  {proposal.status.replaceAll("_", " ")}
                </div>
                <h2>{formatMinorMoney(version.amount_minor, version.currency)}</h2>
                <div className={styles.compareFacts}>
                  <div><span>Delivery</span><strong>{version.delivery_days} days</strong></div>
                  <div><span>Milestones</span><strong>{version.milestones.length || "None"}</strong></div>
                  <div><span>Versions</span><strong>{proposal.versions.length}</strong></div>
                </div>
                <p className={styles.compareLetter}>{version.cover_letter || "No cover letter."}</p>
                <div className={styles.compareFreelancer}>
                  <span>Freelancer</span>
                  <strong>{proposal.freelancer_user_id.slice(0, 8)}</strong>
                </div>
                <div className={styles.compareActions}>
                  <Link href={`/dashboard/proposals/${proposal.id}`}>Review history</Link>
                  {actions
                    .filter((action) => action in EMPLOYER_LABELS)
                    .map((action) => (
                      <button
                        type="button"
                        key={action}
                        data-action={action}
                        disabled={busyId === proposal.id}
                        onClick={() => void transition(proposal, action)}
                      >
                        {EMPLOYER_LABELS[action]}
                      </button>
                    ))}
                </div>
              </article>
            );
          })}
        </section>
      ) : (
        <section className={styles.emptyState}>
          <h2>No proposals yet.</h2>
          <p>This project has no private proposals to compare. The frontend does not synthesize candidates from talent search results.</p>
        </section>
      )}
    </main>
  );
}
