"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useSession } from "@/components/providers/session-provider";
import {
  createRiskAssessment,
  getPriceEstimate,
  getRecommendations,
  getSkillSuggestions,
  listModels,
  listOpenProjects,
  listRiskAssessments,
  recordRecommendationEvent,
  reviewRiskAssessment,
  type ModelRegistryEntry,
  type PriceEstimate,
  type RecommendationRun,
  type RiskAssessment,
  type SkillSuggestionResult,
} from "@/lib/api/ai";
import { ProductApiError } from "@/lib/api/product-client";
import type { Project } from "@/lib/api/work";
import { formatDateTime, formatMinorMoney } from "@/lib/intl";

import styles from "./ai.module.css";

function label(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function errorMessage(error: unknown): string {
  if (error instanceof ProductApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "The AI workspace could not complete that request.";
}

function scorePercent(basisPoints: number): string {
  return `${(basisPoints / 100).toFixed(1)}%`;
}

function priceRange(estimate: PriceEstimate): string {
  if (
    estimate.currency &&
    estimate.lower_minor !== null &&
    estimate.upper_minor !== null
  ) {
    return `${formatMinorMoney(estimate.lower_minor, estimate.currency)} – ${formatMinorMoney(
      estimate.upper_minor,
      estimate.currency,
    )}`;
  }
  return "Not enough evidence for a reliable range";
}

export function AiWorkspace() {
  const { user, status } = useSession();
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [recommendations, setRecommendations] = useState<RecommendationRun | null>(null);
  const [price, setPrice] = useState<PriceEstimate | null>(null);
  const [skills, setSkills] = useState<SkillSuggestionResult | null>(null);
  const [models, setModels] = useState<ModelRegistryEntry[]>([]);
  const [riskItems, setRiskItems] = useState<RiskAssessment[]>([]);
  const [riskCursor, setRiskCursor] = useState<string | null>(null);
  const [riskFilter, setRiskFilter] = useState("PENDING");
  const [subjectUserId, setSubjectUserId] = useState("");
  const [riskText, setRiskText] = useState("");
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const userId = user?.id ?? "";
  const isEmployer = Boolean(user?.roles.includes("employer"));
  const isFreelancer = Boolean(user?.roles.includes("freelancer"));
  const isAdmin = Boolean(user?.roles.includes("admin"));

  useEffect(() => {
    if (status === "anonymous") router.replace("/login?next=/dashboard/ai");
  }, [router, status]);

  const loadProjects = useCallback(async () => {
    if (!userId) return;
    try {
      const result = await listOpenProjects(userId);
      setProjects(result.items);
      setSelectedProjectId((current) => current || result.items[0]?.id || "");
    } catch (error) {
      setFailure(errorMessage(error));
    }
  }, [userId]);

  const loadSkills = useCallback(async () => {
    setBusy("skills");
    setFailure(null);
    try {
      setSkills(await getSkillSuggestions());
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, []);

  const loadAdminData = useCallback(async (filter: string) => {
    setBusy("admin-load");
    setFailure(null);
    try {
      const [modelResult, riskResult] = await Promise.all([
        listModels(),
        listRiskAssessments(filter || null),
      ]);
      setModels(modelResult.items);
      setRiskItems(riskResult.items);
      setRiskCursor(riskResult.next_after);
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }, []);

  useEffect(() => {
    if (status !== "authenticated") return;
    const timer = window.setTimeout(() => {
      if (isEmployer) void loadProjects();
      if (isFreelancer) void loadSkills();
      if (isAdmin) void loadAdminData(riskFilter);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [isAdmin, isEmployer, isFreelancer, loadAdminData, loadProjects, loadSkills, riskFilter, status]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId],
  );

  async function analyzeProject() {
    if (!selectedProjectId) return;
    setBusy("project");
    setFailure(null);
    setNotice(null);
    try {
      const [recommendationResult, priceResult] = await Promise.all([
        getRecommendations(selectedProjectId),
        getPriceEstimate(selectedProjectId),
      ]);
      setRecommendations(recommendationResult);
      setPrice(priceResult);
      await Promise.allSettled(
        recommendationResult.items.map((item) =>
          recordRecommendationEvent(
            recommendationResult.run_id,
            item.freelancer_id,
            "IMPRESSION",
            `impression-${recommendationResult.run_id}-${item.freelancer_id}`,
          ),
        ),
      );
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  function recordProfileView(freelancerId: string) {
    if (!recommendations) return;
    void recordRecommendationEvent(
      recommendations.run_id,
      freelancerId,
      "PROFILE_VIEW",
      `profile-${recommendations.run_id}-${freelancerId}`,
    ).catch(() => undefined);
  }

  async function refreshRiskQueue(filter = riskFilter) {
    setBusy("risk-refresh");
    setFailure(null);
    try {
      const result = await listRiskAssessments(filter || null);
      setRiskItems(result.items);
      setRiskCursor(result.next_after);
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  async function loadOlderRisk() {
    if (!riskCursor) return;
    setBusy("risk-more");
    setFailure(null);
    try {
      const result = await listRiskAssessments(riskFilter || null, riskCursor);
      setRiskItems((current) => [...current, ...result.items]);
      setRiskCursor(result.next_after);
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  async function assessRisk() {
    if (!subjectUserId.trim()) return;
    setBusy("risk-create");
    setFailure(null);
    setNotice(null);
    try {
      const created = await createRiskAssessment(subjectUserId.trim(), riskText);
      setNotice(
        created.review_status === "PENDING"
          ? "Assessment created and queued for human review. No automatic enforcement was applied."
          : "Assessment created. No automatic enforcement was applied.",
      );
      setSubjectUserId("");
      setRiskText("");
      await refreshRiskQueue();
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  async function reviewRisk(item: RiskAssessment, decision: "CLEAR" | "ESCALATE") {
    setBusy(`review-${item.id}`);
    setFailure(null);
    try {
      await reviewRiskAssessment(item.id, decision, reviewNotes[item.id] ?? "");
      await refreshRiskQueue();
    } catch (error) {
      setFailure(errorMessage(error));
    } finally {
      setBusy(null);
    }
  }

  if (status === "loading") {
    return <main className={styles.shell}><p role="status">Opening AI workspace…</p></main>;
  }
  if (!user) return null;

  return (
    <main className={styles.shell}>
      <header className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>AI assistance · versioned and explainable</p>
          <h1>Decision support, not hidden automation.</h1>
          <p>
            Matching, skill detection, pricing, and fraud scoring expose their model versions and evidence.
            Suggestions never rewrite a profile, and risk scores never apply a heavy action by themselves.
          </p>
        </div>
        <Link className={styles.backLink} href="/dashboard">Back to dashboard</Link>
      </header>

      {failure ? <p className={styles.error} role="alert">{failure}</p> : null}
      {notice ? <p className={styles.notice} role="status">{notice}</p> : null}

      {isEmployer ? (
        <section className={styles.section} aria-labelledby="matching-title">
          <div className={styles.sectionHeading}>
            <div><p className={styles.kicker}>Employer</p><h2 id="matching-title">Project matching & pricing</h2></div>
            <p>Generate a fresh, versioned recommendation run for one of your open projects.</p>
          </div>
          <div className={styles.projectControls}>
            <label>
              Open project
              <select value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)}>
                {projects.length === 0 ? <option value="">No open projects</option> : null}
                {projects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}
              </select>
            </label>
            <button type="button" disabled={!selectedProjectId || busy === "project"} onClick={() => void analyzeProject()}>
              {busy === "project" ? "Analyzing…" : "Analyze project"}
            </button>
          </div>
          {selectedProject ? <p className={styles.contextLine}>Skills: {selectedProject.skills.join(", ") || "No explicit skills"}</p> : null}

          {price ? (
            <article className={styles.priceCard}>
              <div><span>Competitive range</span><strong>{priceRange(price)}</strong></div>
              <dl>
                <div><dt>Confidence</dt><dd>{label(price.confidence)}</dd></div>
                <div><dt>Evidence</dt><dd>{price.sample_count} historical samples</dd></div>
                <div><dt>Method</dt><dd>{label(price.method)}</dd></div>
              </dl>
              <small>{price.model_version} · {price.feature_version}</small>
            </article>
          ) : null}

          {recommendations ? (
            <div className={styles.recommendationBlock}>
              <div className={styles.runMeta}>
                <span>Run {recommendations.run_id.slice(0, 8)}</span>
                <span>{recommendations.model_version}</span>
                <span>{recommendations.feature_version}</span>
                <span>candidate set {recommendations.candidate_set_version.slice(0, 10)}</span>
              </div>
              {recommendations.items.length === 0 ? <p>No eligible candidates were found for this run.</p> : null}
              <div className={styles.cards}>
                {recommendations.items.map((item) => (
                  <article className={styles.matchCard} key={item.freelancer_id}>
                    <div className={styles.matchTop}>
                      <span className={styles.rank}>#{item.rank}</span>
                      <strong>{scorePercent(item.score_basis_points)} match</strong>
                    </div>
                    <p className={styles.candidateId}>Candidate {item.freelancer_id.slice(0, 8)}</p>
                    <ul>{item.reasons.map((reason) => <li key={reason}>{label(reason)}</li>)}</ul>
                    <div className={styles.featureGrid}>
                      {Object.entries(item.features).map(([name, value]) => (
                        <div key={name}><span>{label(name)}</span><strong>{Math.round(value * 100)}%</strong></div>
                      ))}
                    </div>
                    <Link href={`/talent/${item.freelancer_id}`} onClick={() => recordProfileView(item.freelancer_id)}>
                      Review profile →
                    </Link>
                  </article>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {isFreelancer ? (
        <section className={styles.section} aria-labelledby="skills-title">
          <div className={styles.sectionHeading}>
            <div><p className={styles.kicker}>Freelancer</p><h2 id="skills-title">Skills we detected</h2></div>
            <button type="button" disabled={busy === "skills"} onClick={() => void loadSkills()}>Refresh suggestions</button>
          </div>
          <p className={styles.guardrail}>Suggestions are advisory only. Your profile is never changed without an explicit edit.</p>
          {skills ? (
            <>
              <div className={styles.runMeta}><span>{skills.model_version}</span><span>{skills.feature_version}</span><span>profile mutated: no</span></div>
              <div className={styles.skillList}>
                {skills.suggestions.length === 0 ? <p>No new skills were detected from your current profile and portfolio.</p> : null}
                {skills.suggestions.map((skill) => (
                  <article key={skill.skill_id}>
                    <div><strong>{skill.name}</strong><span>{Math.round(skill.confidence * 100)}% confidence</span></div>
                    <small>Evidence: {label(skill.evidence_source)}</small>
                  </article>
                ))}
              </div>
              <Link href="/dashboard/profile">Review and edit profile skills →</Link>
            </>
          ) : null}
        </section>
      ) : null}

      {isAdmin ? (
        <section className={styles.section} aria-labelledby="risk-title">
          <div className={styles.sectionHeading}>
            <div><p className={styles.kicker}>Admin</p><h2 id="risk-title">Model registry & human risk review</h2></div>
            <p>Risk scoring is evidence for a reviewer; this workspace never exposes an automatic ban action.</p>
          </div>
          <div className={styles.adminGrid}>
            <div className={styles.adminPanel}>
              <h3>Registered models</h3>
              <div className={styles.modelList}>
                {models.map((model) => (
                  <article key={model.id}>
                    <div><strong>{model.name}</strong><span data-status={model.status}>{model.status}</span></div>
                    <p>{model.version} · {model.feature_version}</p>
                    <small>{model.model_type}</small>
                  </article>
                ))}
              </div>
            </div>
            <div className={styles.adminPanel}>
              <h3>Run explainable assessment</h3>
              <label>Subject user UUID<input value={subjectUserId} onChange={(event) => setSubjectUserId(event.target.value)} placeholder="00000000-0000-4000-8000-000000000000" /></label>
              <label>Context text<textarea value={riskText} onChange={(event) => setRiskText(event.target.value)} rows={5} maxLength={20000} placeholder="Optional text to inspect for URL spam or off-platform contact attempts" /></label>
              <button type="button" disabled={!subjectUserId.trim() || busy === "risk-create"} onClick={() => void assessRisk()}>Assess for human review</button>
            </div>
          </div>

          <div className={styles.queueHeader}>
            <h3>Review queue</h3>
            <label>Status<select value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)}><option value="PENDING">Pending</option><option value="NOT_REQUIRED">Not required</option><option value="CLEARED">Cleared</option><option value="ESCALATED">Escalated</option><option value="">All</option></select></label>
          </div>
          <div className={styles.riskList}>
            {riskItems.length === 0 ? <p>No assessments in this queue.</p> : null}
            {riskItems.map((item) => (
              <article key={item.id} className={styles.riskCard}>
                <div className={styles.riskTop}>
                  <div><strong>{scorePercent(item.risk_score_basis_points)} risk</strong><span>{item.review_status}</span></div>
                  <small>{formatDateTime(item.created_at)}</small>
                </div>
                <p>Subject {item.subject_user_id}</p>
                <div className={styles.reasonList}>{item.reasons.length ? item.reasons.map((reason) => <span key={reason}>{label(reason)}</span>) : <span>No scored risk reasons</span>}</div>
                <details><summary>Signals</summary><pre>{JSON.stringify(item.signals, null, 2)}</pre></details>
                <small>{item.model_version} · {item.feature_version} · automatic action: none</small>
                {item.review_status === "PENDING" ? (
                  <div className={styles.reviewControls}>
                    <label>Reviewer note<input value={reviewNotes[item.id] ?? ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [item.id]: event.target.value }))} maxLength={2000} /></label>
                    <div><button type="button" disabled={busy === `review-${item.id}`} onClick={() => void reviewRisk(item, "CLEAR")}>Clear</button><button type="button" className={styles.secondaryButton} disabled={busy === `review-${item.id}`} onClick={() => void reviewRisk(item, "ESCALATE")}>Escalate</button></div>
                  </div>
                ) : item.review_note ? <p>Review note: {item.review_note}</p> : null}
              </article>
            ))}
          </div>
          {riskCursor ? <button type="button" className={styles.secondaryButton} disabled={busy === "risk-more"} onClick={() => void loadOlderRisk()}>Load older assessments</button> : null}
        </section>
      ) : null}
    </main>
  );
}
