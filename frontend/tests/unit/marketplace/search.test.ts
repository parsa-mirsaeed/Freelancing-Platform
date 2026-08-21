import { describe, expect, it } from "vitest";

import {
  buildTalentSearchPath,
  parseTalentSearchParams,
  splitSkillInput,
} from "@/lib/marketplace/search";

describe("talent search state", () => {
  it("parses repeated skills, availability, and bounded limit", () => {
    expect(parseTalentSearchParams({
      q: "  backend engineer  ",
      skill: ["Python", "PostgreSQL"],
      available: "true",
      limit: "999",
    })).toEqual({
      query: "backend engineer",
      skills: ["Python", "PostgreSQL"],
      available: true,
      limit: 50,
    });
  });

  it("serializes repeated skill parameters instead of comma-joining them", () => {
    const path = buildTalentSearchPath({
      query: "platform",
      skills: ["Python", "React"],
      available: false,
      limit: 12,
    });
    const url = new URL(path, "https://example.test");
    expect(url.pathname).toBe("/api/v1/search/freelancers");
    expect(url.searchParams.getAll("skill")).toEqual(["Python", "React"]);
    expect(url.searchParams.get("available")).toBe("false");
    expect(url.searchParams.get("limit")).toBe("12");
  });

  it("deduplicates comma-entered skill filters", () => {
    expect(splitSkillInput("Python, React, Python,  PostgreSQL ")).toEqual([
      "Python",
      "React",
      "PostgreSQL",
    ]);
  });
});
