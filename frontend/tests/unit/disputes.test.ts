import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  attachEvidence,
  listDisputes,
  openDispute,
  requestEvidenceUpload,
  resolveDispute,
  transitionDispute,
} from "@/lib/api/disputes";

vi.mock("@/lib/api/product-client", () => ({
  productJson: vi.fn(async () => ({ ok: true })),
}));

import { productJson } from "@/lib/api/product-client";

describe("dispute API contract", () => {
  beforeEach(() => {
    vi.mocked(productJson).mockReset();
    vi.mocked(productJson).mockResolvedValue({ ok: true });
  });

  it("lists only the requested cursor-bounded dispute page", async () => {
    await listDisputes({ after: "case-1", limit: 25, status: "UNDER_REVIEW" });
    expect(productJson).toHaveBeenCalledWith(
      "disputes?limit=25&after=case-1&status=UNDER_REVIEW",
      { signal: undefined },
    );
  });

  it("opens a milestone dispute with an explicit reason", async () => {
    await openDispute("milestone-7", "Scope mismatch");
    expect(productJson).toHaveBeenCalledWith("milestones/milestone-7/disputes", {
      method: "POST",
      body: JSON.stringify({ reason: "Scope mismatch" }),
    });
  });

  it("reserves evidence only for the dispute-evidence file purpose", async () => {
    const file = new File(["evidence"], "proof.pdf", { type: "application/pdf" });
    await requestEvidenceUpload(file);
    expect(productJson).toHaveBeenCalledWith("files/uploads", {
      method: "POST",
      body: JSON.stringify({
        original_name: "proof.pdf",
        mime_type: "application/pdf",
        size_bytes: 8,
        purpose: "DISPUTE_EVIDENCE",
      }),
    });
  });

  it("attaches only a backend file id and immutable note", async () => {
    await attachEvidence("case-9", "file-safe", "Invoice proves the requested scope");
    expect(productJson).toHaveBeenCalledWith("disputes/case-9/evidence", {
      method: "POST",
      body: JSON.stringify({
        file_id: "file-safe",
        note: "Invoice proves the requested scope",
      }),
    });
  });

  it("records admin transition reasons and idempotent exact split payloads", async () => {
    await transitionDispute("case-9", "UNDER_REVIEW", "Evidence window complete");
    expect(productJson).toHaveBeenLastCalledWith("disputes/case-9/transitions", {
      method: "POST",
      body: JSON.stringify({
        to_status: "UNDER_REVIEW",
        reason: "Evidence window complete",
      }),
    });

    await resolveDispute({
      disputeId: "case-9",
      outcome: "SPLIT",
      reason: "Evidence supports an exact allocation",
      freelancerAwardMinor: 6000,
      clientRefundMinor: 4000,
      idempotencyKey: "stable-resolution-key",
    });
    expect(productJson).toHaveBeenLastCalledWith("disputes/case-9/resolve", {
      method: "POST",
      headers: { "Idempotency-Key": "stable-resolution-key" },
      body: JSON.stringify({
        outcome: "SPLIT",
        reason: "Evidence supports an exact allocation",
        freelancer_award_minor: 6000,
        client_refund_minor: 4000,
      }),
    });
  });
});
