"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { useSession } from "@/components/providers/session-provider";
import { productJson } from "@/lib/api/product-client";
import type { Project } from "@/lib/api/work";
import { normalizeWorkSkills, parseProjectBudget } from "@/lib/api/work";
import { formatMinorMoney, minorMoneyInputValue } from "@/lib/intl";

import styles from "./workspace.module.css";

function budgetLabel(project: Project): string {
  if (project.budget_min_minor === null || project.budget_max_minor === null || !project.currency) {
    return "No public budget range";
  }
  return `${formatMinorMoney(project.budget_min_minor, project.currency)} – ${formatMinorMoney(project.budget_max_minor, project.currency)}`;
}

export function ProjectWorkspace() {
  const { user, status } = useSession();
  const [items, setItems] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [budgetMin, setBudgetMin] = useState("");
  const [budgetMax, setBudgetMax] = useState("");
  const [currency, setCurrency] = useState("");
  const [skills, setSkills] = useState("");

  useEffect(() => {
    if (status !== "authenticated" || !user?.roles.includes("employer")) return;
    const controller = new AbortController();
    void productJson<{ items: Project[] }>("projects", { signal: controller.signal })
      .then((payload) => {
        setItems(payload.items.filter((project) => project.employer_user_id === user.id));
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Unable to load projects.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [status, user]);

  function resetEditor() {
    setEditingId(null);
    setTitle("");
    setDescription("");
    setBudgetMin("");
    setBudgetMax("");
    setCurrency("");
    setSkills("");
    setError("");
  }

  function editProject(project: Project) {
    setEditingId(project.id);
    setTitle(project.title);
    setDescription(project.description);
    setSkills(project.skills.join(", "));
    if (project.budget_min_minor !== null && project.budget_max_minor !== null && project.currency) {
      setBudgetMin(minorMoneyInputValue(project.budget_min_minor, project.currency));
      setBudgetMax(minorMoneyInputValue(project.budget_max_minor, project.currency));
      setCurrency(project.currency);
    } else {
      setBudgetMin("");
      setBudgetMax("");
      setCurrency("");
    }
    setMessage("");
    setError("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const payload = {
        title: title.trim(),
        description: description.trim(),
        skills: normalizeWorkSkills(skills),
        ...parseProjectBudget(budgetMin, budgetMax, currency),
      };
      if (!payload.title || !payload.description) throw new RangeError("Title and description are required.");
      const saved = await productJson<Project>(editingId ? `projects/${editingId}` : "projects", {
        method: editingId ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      setItems((current) => {
        const exists = current.some((item) => item.id === saved.id);
        return exists ? current.map((item) => (item.id === saved.id ? saved : item)) : [saved, ...current];
      });
      setMessage(editingId ? "Project brief updated." : "Project published.");
      if (!editingId) resetEditor();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save project.");
    } finally {
      setSaving(false);
    }
  }

  async function closeProject(project: Project) {
    const confirmed = window.confirm(
      `Close “${project.title}”? The backend will allow this only when the contract is active and every current milestone is released.`,
    );
    if (!confirmed) return;
    setError("");
    setMessage("");
    try {
      const closed = await productJson<Project>(`projects/${project.id}/close`, { method: "POST" });
      setItems((current) => current.filter((item) => item.id !== closed.id));
      if (editingId === closed.id) resetEditor();
      setMessage("Project closed after backend completion checks passed.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to close project.");
    }
  }

  if (status === "loading") {
    return <section className={styles.loading} role="status">Opening your employer workspace…</section>;
  }
  if (status !== "authenticated" || !user) {
    return <section className={styles.loading}>Sign in with an employer account to manage projects.</section>;
  }
  if (!user.roles.includes("employer")) {
    return <section className={styles.loading}>Project publishing is available to employer accounts.</section>;
  }
  if (loading) return <section className={styles.loading} role="status">Loading your open projects…</section>;

  return (
    <div className={styles.workspace}>
      <section className={styles.workspaceIntro}>
        <div><p>Employer projects</p><h1>Publish a brief that makes proposal quality comparable.</h1><span>Open projects remain editable. Closing is a backend-governed terminal transition that requires an active contract and released current milestones.</span></div>
        <Link href="/projects">View public projects ↗</Link>
      </section>

      <section className={styles.twoColumn}>
        <div className={styles.inventory}>
          <div className={styles.sectionTitle}><div><span>Open inventory</span><h2>Your project briefs</h2></div><button type="button" onClick={resetEditor}>New project</button></div>
          {items.length ? items.map((project) => (
            <article className={styles.inventoryCard} key={project.id}>
              <div><span>{project.status}</span><h3>{project.title}</h3><p>{project.description}</p><small>{budgetLabel(project)}</small></div>
              <div className={styles.inventoryActions}><Link href={`/projects/${project.id}`}>Public view</Link><button type="button" onClick={() => editProject(project)}>Edit</button><button className={styles.danger} type="button" onClick={() => void closeProject(project)}>Close</button></div>
            </article>
          )) : <p className={styles.empty}>No open projects yet. Publish a brief from the editor.</p>}
          <p className={styles.constraintNote}>The current list endpoint returns OPEN projects only. Closed projects are authoritative backend history but are not listable from this endpoint yet.</p>
        </div>

        <form className={styles.editor} onSubmit={submit}>
          <div className={styles.sectionTitle}><div><span>{editingId ? "Edit project" : "New project"}</span><h2>{editingId ? "Refine the open brief" : "Publish a clear brief"}</h2></div></div>
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
          {message ? <p className={styles.success} role="status">{message}</p> : null}
          <label>Project title<input value={title} maxLength={180} onChange={(event) => setTitle(event.target.value)} required /></label>
          <label>Description<textarea value={description} rows={6} onChange={(event) => setDescription(event.target.value)} required /></label>
          <label>Skills <span>comma separated</span><input value={skills} onChange={(event) => setSkills(event.target.value)} placeholder="Python, PostgreSQL, Product Design" /></label>
          <fieldset className={styles.budget}><legend>Optional budget range</legend><p>Leave all three fields blank to publish without a range. If one is supplied, all are required.</p><div>
            <label>Minimum<input inputMode="decimal" value={budgetMin} onChange={(event) => setBudgetMin(event.target.value)} /></label>
            <label>Maximum<input inputMode="decimal" value={budgetMax} onChange={(event) => setBudgetMax(event.target.value)} /></label>
            <label>Currency<input value={currency} maxLength={3} onChange={(event) => setCurrency(event.target.value.toUpperCase())} /></label>
          </div></fieldset>
          <div className={styles.editorActions}><button type="submit" disabled={saving}>{saving ? "Saving…" : editingId ? "Save project" : "Publish project"}</button>{editingId ? <button type="button" onClick={resetEditor}>Cancel edit</button> : null}</div>
        </form>
      </section>
    </div>
  );
}
