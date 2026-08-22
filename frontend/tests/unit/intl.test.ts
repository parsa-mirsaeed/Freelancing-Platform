import { describe, expect, it } from "vitest";

import { currencyFractionDigits, formatMinorMoney } from "@/lib/intl";

describe("international money formatting", () => {
  it("uses currency-specific minor-unit exponents", () => {
    expect(currencyFractionDigits("USD")).toBe(2);
    expect(currencyFractionDigits("JPY")).toBe(0);
    expect(currencyFractionDigits("BHD")).toBe(3);
  });

  it("never assumes every currency has two fraction digits", () => {
    expect(formatMinorMoney(12345, "USD", "en-US")).toContain("123.45");
    expect(formatMinorMoney(12345, "JPY", "ja-JP")).toContain("12,345");
    expect(formatMinorMoney(12345, "BHD", "en-US")).toContain("12.345");
  });

  it("rejects unsafe integer money values", () => {
    expect(() => formatMinorMoney(Number.MAX_VALUE, "USD")).toThrow(TypeError);
  });
});
