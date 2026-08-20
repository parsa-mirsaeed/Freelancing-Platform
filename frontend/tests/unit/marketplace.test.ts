import { describe, expect, it } from "vitest";

import { averageReviewRating, normalizeSkillFilters, talentSearchPath } from "@/lib/api/marketplace";

describe("marketplace query model", () => {
  it("normalizes comma-separated skill filters and removes duplicates", () => {
    expect(normalizeSkillFilters(["React, Product Design", "React", "  research "])).toEqual([
      "React",
      "Product Design",
      "research",
    ]);
  });

  it("encodes repeated backend skill parameters and bounded limits", () => {
    const path = talentSearchPath({ query: "product", skills: ["design, react"], available: true, limit: 500 });
    expect(path).toContain("q=product");
    expect(path).toContain("skill=design");
    expect(path).toContain("skill=react");
    expect(path).toContain("available=true");
    expect(path).toContain("limit=50");
  });

  it("derives review averages only from received reviews", () => {
    expect(averageReviewRating([])).toBeNull();
    expect(averageReviewRating([
      { id: "1", project_id: "p1", reviewer_user_id: "u1", freelancer_user_id: "f1", rating: 5, comment: "", created_at: "2026-01-01T00:00:00Z" },
      { id: "2", project_id: "p2", reviewer_user_id: "u2", freelancer_user_id: "f1", rating: 4, comment: "", created_at: "2026-01-02T00:00:00Z" },
    ])).toBe(4.5);
  });
});
