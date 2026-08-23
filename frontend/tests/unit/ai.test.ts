import { beforeEach, describe, expect, it, vi } from "vitest";

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
} from "@/lib/api/ai";

vi.mock("@/lib/api/product-client", () => ({
  productJson: vi.fn(),
}));

import { productJson } from "@/lib/api/product-client";

describe("AI product API contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(productJson).mockResolvedValue({});
  });

  it("filters the public project catalog to the employer's own open projects", async () => {
    vi.mocked(productJson).mockResolvedValueOnce({
      items: [
        {
          id: "own-open",
          employer_user_id: "employer-1",
          title: "Owned open project",
          description: "",
          budget_min_minor: null,
          budget_max_minor: null,
          currency: null,
          status: "OPEN",
          skills: [],
        },
        {
          id: "foreign-open",
          employer_user_id: "employer-2",
          title: "Foreign open project",
          description: "",
          budget_min_minor: null,
          budget_max_minor: null,
          currency: null,
          status: "OPEN",
          skills: [],
        },
        {
          id: "own-closed",
          employer_user_id: "employer-1",
          title: "Owned closed project",
          description: "",
          budget_min_minor: null,
          budget_max_minor: null,
          currency: null,
          status: "CLOSED",
          skills: [],
        },
      ],
    });

    const result = await listOpenProjects("employer-1");
    expect(result.items.map((project) => project.id)).toEqual(["own-open"]);
    expect(productJson).toHaveBeenCalledWith("projects");
  });

  it("uses versioned project recommendation and price endpoints", async () => {
    await getRecommendations("project-1", 99);
    await getPriceEstimate("project-1");

    expect(productJson).toHaveBeenNthCalledWith(
      1,
      "projects/project-1/recommendations?limit=20",
    );
    expect(productJson).toHaveBeenNthCalledWith(
      2,
      "projects/project-1/ai/price-estimate",
    );
  });

  it("records only explicit low-stakes recommendation events with a client event id", async () => {
    await recordRecommendationEvent("run-1", "freelancer-1", "PROFILE_VIEW", "view-1");

    expect(productJson).toHaveBeenCalledWith("recommendations/run-1/events", {
      method: "POST",
      body: JSON.stringify({
        freelancer_user_id: "freelancer-1",
        event_type: "PROFILE_VIEW",
        client_event_id: "view-1",
      }),
    });
  });

  it("keeps skill suggestions read-only at the API boundary", async () => {
    await getSkillSuggestions();
    expect(productJson).toHaveBeenCalledWith("freelancers/me/ai/skill-suggestions");
  });

  it("queries the human risk-review queue with bounded cursor pagination", async () => {
    await listRiskAssessments("PENDING", "assessment-1", 500);
    expect(productJson).toHaveBeenCalledWith(
      "admin/risk/assessments?limit=100&status=PENDING&after=assessment-1",
    );
  });

  it("keeps fraud assessment and human review as separate admin actions", async () => {
    await createRiskAssessment("user-1", "pay outside the platform");
    await reviewRiskAssessment("assessment-1", "ESCALATE", "Needs investigation");
    await listModels();

    expect(productJson).toHaveBeenNthCalledWith(1, "admin/risk/assessments", {
      method: "POST",
      body: JSON.stringify({ subject_user_id: "user-1", text: "pay outside the platform" }),
    });
    expect(productJson).toHaveBeenNthCalledWith(2, "admin/risk/assessments/assessment-1/review", {
      method: "POST",
      body: JSON.stringify({ decision: "ESCALATE", note: "Needs investigation" }),
    });
    expect(productJson).toHaveBeenNthCalledWith(3, "admin/ml/models");
  });
});
