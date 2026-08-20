import { describe, expect, it } from "vitest";

import type { Gig } from "@/lib/api/work";
import {
  minimumGigPackage,
  normalizeWorkSkills,
  parseProjectBudget,
  sortGigPackages,
} from "@/lib/api/work";

describe("work domain presentation helpers", () => {
  it("orders packages by the backend tier contract", () => {
    const gig = {
      packages: [
        { id: "p", tier: "PREMIUM", amount_minor: 30000, currency: "USD", delivery_days: 5, revisions: 3, description: "" },
        { id: "b", tier: "BASIC", amount_minor: 10000, currency: "USD", delivery_days: 2, revisions: 1, description: "" },
        { id: "s", tier: "STANDARD", amount_minor: 20000, currency: "USD", delivery_days: 3, revisions: 2, description: "" },
      ],
    } as Gig;
    expect(sortGigPackages(gig.packages).map((item) => item.tier)).toEqual([
      "BASIC",
      "STANDARD",
      "PREMIUM",
    ]);
    expect(minimumGigPackage(gig)?.tier).toBe("BASIC");
  });

  it("converts a complete project budget without floating point money arithmetic", () => {
    expect(parseProjectBudget("12.345", "20.001", "KWD")).toEqual({
      budget_min_minor: 12345,
      budget_max_minor: 20001,
      currency: "KWD",
    });
  });

  it("allows a deliberately unspecified budget but rejects partial ranges", () => {
    expect(parseProjectBudget("", "", "")).toEqual({
      budget_min_minor: null,
      budget_max_minor: null,
      currency: null,
    });
    expect(() => parseProjectBudget("100", "", "USD")).toThrow(/provided together/i);
    expect(() => parseProjectBudget("200", "100", "USD")).toThrow(/maximum budget/i);
  });

  it("normalizes comma-separated project skills without duplicates", () => {
    expect(normalizeWorkSkills("Python, PostgreSQL, Python, Product Design")).toEqual([
      "Python",
      "PostgreSQL",
      "Product Design",
    ]);
  });
});
