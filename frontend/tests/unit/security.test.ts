import { describe, expect, it } from "vitest";

import { hasFreshMfa, needsMfaEnrollment, type MfaStatus } from "@/lib/api/security";

const NOW = Date.parse("2026-08-23T10:00:00Z");

function status(overrides: Partial<MfaStatus> = {}): MfaStatus {
  return {
    enabled: false,
    verified_until: null,
    recovery_codes_remaining: 0,
    ...overrides,
  };
}

describe("identity security helpers", () => {
  it("distinguishes enrollment from session step-up", () => {
    expect(needsMfaEnrollment(status())).toBe(true);
    expect(needsMfaEnrollment(status({ enabled: true }))).toBe(false);
  });

  it("treats only a future session verification as fresh", () => {
    expect(
      hasFreshMfa(status({ enabled: true, verified_until: "2026-08-23T10:05:00Z" }), NOW),
    ).toBe(true);
    expect(
      hasFreshMfa(status({ enabled: true, verified_until: "2026-08-23T09:59:59Z" }), NOW),
    ).toBe(false);
    expect(hasFreshMfa(status({ enabled: true, verified_until: "invalid" }), NOW)).toBe(false);
  });
});
