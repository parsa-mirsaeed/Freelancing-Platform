import { describe, expect, it } from "vitest";

import { majorMoneyToMinor, minorMoneyToMajor } from "@/lib/marketplace/money-input";

describe("minor-unit form conversion", () => {
  it("handles ordinary two-decimal currencies exactly", () => {
    expect(majorMoneyToMinor("120.50", "USD")).toBe(12050);
    expect(minorMoneyToMajor(12050, "USD")).toBe("120.5");
  });

  it("respects zero-decimal currencies", () => {
    expect(majorMoneyToMinor("5000", "JPY")).toBe(5000);
    expect(() => majorMoneyToMinor("5000.5", "JPY")).toThrow(/decimal places/i);
  });

  it("respects three-decimal currencies", () => {
    expect(majorMoneyToMinor("12.345", "KWD")).toBe(12345);
    expect(minorMoneyToMajor(12345, "KWD")).toBe("12.345");
  });

  it("rejects negative, malformed, and unsafe values", () => {
    expect(() => majorMoneyToMinor("-10", "USD")).toThrow();
    expect(() => majorMoneyToMinor("1.2.3", "USD")).toThrow();
    expect(() => majorMoneyToMinor("999999999999999999999", "USD")).toThrow(/too large/i);
  });
});
