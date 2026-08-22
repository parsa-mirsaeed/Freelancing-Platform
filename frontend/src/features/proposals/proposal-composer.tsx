"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import { ProductApiError, productJson } from "@/lib/api/product-client";
import type { Proposal, ProposalWritePayload } from "@/lib/api/proposals";
import type { Project } from "@/lib/api/work";
import { formatMinorMoney } from "@/lib/intl";

import { ProposalEditor } from "./proposal-editor";
import styles from "./proposals.module.css";

function projectBudget(project: Project): string {
  if (
    project.budget_min_minor === null ||
    project.budget_max_minor === null ||
    project.currency === null
  ) {
    return "No published budget range";
  }
  return `${formatMinorMoney(project.budget_min_minor, project.currency)} – ${formatMinorMoney(project.budget_max_minor, project.currency)}`;
}

export function ProposalComposer({ projectId }: { projectId: string }) {
  const { user, status } = useSession();
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (status !== "authenticated" || !user?.roles.includes("freelancer")) return;
    const controller = new AbortController();
    void productJson<Project>(`projects/${projectId}`, { signal: controller.signal })
      .then((value) => {
        setProject(value);
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load the project brief.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [projectId, status, user]);

  async function saveDraft(payload: ProposalWritePayload) {
    setSaving(true);
    setError("");
    try {
      const proposal = await productJson<Proposal>(`projects/${projectId}/proposals`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      router.push(`/dashboard/proposals/${proposal.id}`);
    } catch (reason) {
      if (reason instanceof ProductApiError && reason.status === 409) {
        setError("A proposal already exists for this project. Open the existing proposal from its direct link to continue negotiation.");
      } else {
        setError(reason instanceof Error ? reason.message : "Unable to save proposal draft.");
      }
    } finally {
      setSaving(false);
    }
  }

  if (status === "loading") {
    return <section className={styles.loading} role="status">Checking your marketplace session…</section>;
  }
  if (status !== "authenticated" || !user) {
    return (
      <section className={styles.accessState}>
        <h1>Sign in to submit a proposal.</h1>
        <p>Proposal drafts are private commercial records and require a freelancer account.</p>
        <Link href={`/login?next=/projects/${projectId}/proposal`}>Sign in</Link>
      </section>
    );
  }
  if (!user.roles.includes("freelancer")) {
    return (
      <section className={styles.accessState}>
        <h1>Freelancer account required.</h1>
        <p>Employers compare proposals from their project workspace rather than submitting to their own briefs.</p>
        <Link href={`/dashboard/projects/${projectId}/proposals`}>Open proposal comparison</Link>
      </section>
    );
  }
  if (loading) return <section className={styles.loading} role="status">Loading project terms…</section>;
  if (!project) {
    return <section className={styles.accessState}><h1>Project unavailable.</h1><p>{error || "The project could not be loaded."}</p></section>;
  }

  return (
    <main className={styles.composerPage}>
      <section className={styles.composerHero}>
        <div>
          <Link href={`/projects/${project.id}`}>← Back to project brief</Link>
          <p>Private commercial draft</p>
          <h1>Propose a clear delivery plan.</h1>
          <span>
            This first save creates version 1 in <strong>DRAFT</strong>. Submission is a separate
            state transition so you can review the immutable commercial record before sending it.
          </span>
        </div>
        <aside>
          <span>Project</span>
          <strong>{project.title}</strong>
          <dl>
            <div><dt>Published budget</dt><dd>{projectBudget(project)}</dd></div>
            <div><dt>Project currency</dt><dd>{project.currency ?? "Chosen in proposal"}</dd></div>
            <div><dt>Status</dt><dd>{project.status}</dd></div>
          </dl>
        </aside>
      </section>

      {error ? <p className={styles.errorBanner} role="alert">{error}</p> : null}
      <ProposalEditor
        projectCurrency={project.currency}
        submitLabel="Save proposal draft"
        busy={saving}
        onSubmit={saveDraft}
      />
    </main>
  );
}
