import { describe, expect, it } from "vitest";

import { isProxyPathAllowed } from "@/lib/server/proxy-policy";

describe("browser backend proxy policy", () => {
  it("allows normal authenticated product APIs", () => {
    expect(isProxyPathAllowed(["projects", "123", "contract"])).toBe(true);
    expect(isProxyPathAllowed(["wallet"])).toBe(true);
  });

  it("blocks token exchange and webhook endpoints", () => {
    expect(isProxyPathAllowed(["auth", "login"])).toBe(false);
    expect(isProxyPathAllowed(["auth", "refresh"])).toBe(false);
    expect(isProxyPathAllowed(["payments", "webhooks", "sandbox"])).toBe(false);
  });

  it("blocks traversal-like segments", () => {
    expect(isProxyPathAllowed(["projects", "..", "admin"])).toBe(false);
  });
});
