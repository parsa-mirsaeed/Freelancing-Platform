import { productJson } from "@/lib/api/product-client";
import type { Project } from "@/lib/api/work";

export interface RecommendationItem {
  freelancer_id: string;
  rank: number;
  score: number;
  score_basis_points: number;
  features: Record<string, number>;
  reasons: string[];
}

export interface RecommendationRun {
  run_id: string;
  project_id: string;
  model_version: string;
  feature_version: string;
  candidate_set_version: string;
  items: RecommendationItem[];
}

export interface PriceEstimate {
  project_id: string;
  model_version: string;
  feature_version: string;
  currency: string | null;
  lower_minor: number | null;
  upper_minor: number | null;
  sample_count: number;
  confidence: "MEDIUM" | "LOW" | "BUDGET_ONLY" | "INSUFFICIENT" | string;
  method: string;
}

export interface SkillSuggestion {
  skill_id: string;
  name: string;
  slug: string;
  confidence: number;
  evidence_source: string;
}

export interface SkillSuggestionResult {
  model_version: string;
  feature_version: string;
  profile_mutated: false;
  suggestions: SkillSuggestion[];
}

export interface ModelRegistryEntry {
  id: string;
  name: string;
  version: string;
  model_type: string;
  feature_version: string;
  status: string;
  config: Record<string, unknown>;
  metrics: Record<string, unknown>;
  artifact_uri: string | null;
  created_at: string;
}

export interface RiskAssessment {
  id: string;
  subject_user_id: string;
  model_version: string;
  feature_version: string;
  risk_score: number;
  risk_score_basis_points: number;
  reasons: string[];
  signals: Record<string, unknown>;
  review_status: "NOT_REQUIRED" | "PENDING" | "CLEARED" | "ESCALATED" | string;
  reviewer_user_id: string | null;
  review_note: string | null;
  created_at: string;
  reviewed_at: string | null;
  automatic_action: null;
}

export interface RiskAssessmentPage {
  items: RiskAssessment[];
  next_after: string | null;
}

export async function listOpenProjects(employerUserId: string): Promise<{ items: Project[] }> {
  const result = await productJson<{ items: Project[] }>("projects");
  return {
    items: result.items.filter(
      (project) => project.employer_user_id === employerUserId && project.status === "OPEN",
    ),
  };
}

export function getRecommendations(projectId: string, limit = 8): Promise<RecommendationRun> {
  const safeLimit = Math.min(20, Math.max(1, Math.trunc(limit)));
  return productJson<RecommendationRun>(
    `projects/${encodeURIComponent(projectId)}/recommendations?limit=${safeLimit}`,
  );
}

export function recordRecommendationEvent(
  runId: string,
  freelancerUserId: string,
  eventType: "IMPRESSION" | "PROFILE_VIEW",
  clientEventId: string,
): Promise<{ id: string; created: boolean }> {
  return productJson<{ id: string; created: boolean }>(
    `recommendations/${encodeURIComponent(runId)}/events`,
    {
      method: "POST",
      body: JSON.stringify({
        freelancer_user_id: freelancerUserId,
        event_type: eventType,
        client_event_id: clientEventId,
      }),
    },
  );
}

export function getPriceEstimate(projectId: string): Promise<PriceEstimate> {
  return productJson<PriceEstimate>(`projects/${encodeURIComponent(projectId)}/ai/price-estimate`);
}

export function getSkillSuggestions(): Promise<SkillSuggestionResult> {
  return productJson<SkillSuggestionResult>("freelancers/me/ai/skill-suggestions");
}

export function listModels(): Promise<{ items: ModelRegistryEntry[] }> {
  return productJson<{ items: ModelRegistryEntry[] }>("admin/ml/models");
}

export function listRiskAssessments(
  status: string | null = "PENDING",
  after: string | null = null,
  limit = 25,
): Promise<RiskAssessmentPage> {
  const params = new URLSearchParams({
    limit: String(Math.min(100, Math.max(1, Math.trunc(limit)))),
  });
  if (status) params.set("status", status);
  if (after) params.set("after", after);
  return productJson<RiskAssessmentPage>(`admin/risk/assessments?${params.toString()}`);
}

export function createRiskAssessment(subjectUserId: string, text: string): Promise<RiskAssessment> {
  return productJson<RiskAssessment>("admin/risk/assessments", {
    method: "POST",
    body: JSON.stringify({ subject_user_id: subjectUserId, text }),
  });
}

export function reviewRiskAssessment(
  assessmentId: string,
  decision: "CLEAR" | "ESCALATE",
  note: string,
): Promise<RiskAssessment> {
  return productJson<RiskAssessment>(`admin/risk/assessments/${assessmentId}/review`, {
    method: "POST",
    body: JSON.stringify({ decision, note }),
  });
}
