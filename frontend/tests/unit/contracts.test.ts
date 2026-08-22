import { describe, expect, it, vi } from "vitest";

import {
  canOfferContractCancellation,
  canSignCurrentVersion,
  hasSignedCurrentVersion,
  memberRoleForContract,
  milestoneActions,
  signContract,
  type Contract,
  type Milestone,
} from "@/lib/api/contracts";

vi.mock("@/lib/api/product-client", () => ({
  productJson: vi.fn(async () => ({ ok: true })),
}));

import { productJson } from "@/lib/api/product-client";

const freelancerId = "11111111-1111-4111-8111-111111111111";
const employerId = "22222222-2222-4222-8222-222222222222";
const hash = "a".repeat(64);

function milestone(status: Milestone["status"]): Milestone {
  return {
    id: "33333333-3333-4333-8333-333333333333",
    sequence: 1,
    title: "Delivery",
    amount_minor: 120000,
    currency: "USD",
    delivery_days: 10,
    status,
    events: [],
  };
}

function contract(overrides: Partial<Contract> = {}): Contract {
  return {
    id: "44444444-4444-4444-8444-444444444444",
    project_id: "55555555-5555-4555-8555-555555555555",
    accepted_proposal_id: "66666666-6666-4666-8666-666666666666",
    employer_user_id: employerId,
    freelancer_user_id: freelancerId,
    status: "PENDING_SIGNATURES",
    current_version: 1,
    created_at: "2026-08-22T12:00:00Z",
    activated_at: null,
    cancelled_at: null,
    parties: [
      { user_id: employerId, role: "EMPLOYER", required_signature: true },
      { user_id: freelancerId, role: "FREELANCER", required_signature: true },
    ],
    version: {
      id: "77777777-7777-4777-8777-777777777777",
      version_number: 1,
      document_hash: hash,
      snapshot: {
        scope: { project_title: "Accessible marketplace checkout" },
        price: { amount_minor: 120000 },
        currency: "USD",
      },
      created_at: "2026-08-22T12:00:00Z",
      signatures: [],
      milestones: [milestone("CREATED")],
    },
    ...overrides,
  };
}

describe("contract party and signature affordances", () => {
  it("derives member role only from authoritative contract party ids", () => {
    const value = contract();
    expect(memberRoleForContract(value, freelancerId)).toBe("freelancer");
    expect(memberRoleForContract(value, employerId)).toBe("employer");
    expect(memberRoleForContract(value, "99999999-9999-4999-8999-999999999999")).toBeNull();
  });

  it("offers signing only to a required unsigned party on a non-cancelled contract", () => {
    const value = contract();
    expect(canSignCurrentVersion(value, freelancerId)).toBe(true);
    expect(hasSignedCurrentVersion(value, freelancerId)).toBe(false);

    const signed = contract({
      version: {
        ...value.version,
        signatures: [
          {
            id: "88888888-8888-4888-8888-888888888888",
            user_id: freelancerId,
            signed_at: "2026-08-22T12:05:00Z",
            document_hash: hash,
            signature_provider_reference: null,
          },
        ],
      },
    });
    expect(hasSignedCurrentVersion(signed, freelancerId)).toBe(true);
    expect(canSignCurrentVersion(signed, freelancerId)).toBe(false);
    expect(canSignCurrentVersion({ ...value, status: "CANCELLED" }, employerId)).toBe(false);
  });

  it("sends the backend document hash unchanged with the caller's idempotency key", async () => {
    const value = contract();
    await signContract(value, "signature-intent-123");
    expect(productJson).toHaveBeenCalledWith(`contracts/${value.id}/sign`, {
      method: "POST",
      headers: { "Idempotency-Key": "signature-intent-123" },
      body: JSON.stringify({ document_hash: hash }),
    });
  });

  it("does not offer cancellation after any milestone leaves CREATED", () => {
    const value = contract();
    expect(canOfferContractCancellation(value, "employer")).toBe(true);
    expect(canOfferContractCancellation(value, "freelancer")).toBe(false);
    expect(
      canOfferContractCancellation(
        { ...value, version: { ...value.version, milestones: [milestone("FUNDED")] } },
        "employer",
      ),
    ).toBe(false);
  });
});

describe("milestone state affordances", () => {
  it("mirrors the backend execution transition table", () => {
    expect(milestoneActions(milestone("FUNDED"), "freelancer", "ACTIVE")).toEqual(["start"]);
    expect(milestoneActions(milestone("IN_PROGRESS"), "freelancer", "ACTIVE")).toEqual(["submit"]);
    expect(milestoneActions(milestone("CHANGES_REQUESTED"), "freelancer", "ACTIVE")).toEqual([
      "submit",
    ]);
    expect(milestoneActions(milestone("SUBMITTED"), "employer", "ACTIVE")).toEqual([
      "request-changes",
      "approve",
    ]);
    expect(milestoneActions(milestone("APPROVED"), "employer", "ACTIVE")).toEqual([]);
    expect(milestoneActions(milestone("DISPUTED"), "freelancer", "ACTIVE")).toEqual([]);
  });

  it("offers no milestone execution controls until the contract is ACTIVE", () => {
    expect(milestoneActions(milestone("FUNDED"), "freelancer", "PENDING_SIGNATURES")).toEqual([]);
    expect(milestoneActions(milestone("SUBMITTED"), "employer", "CANCELLED")).toEqual([]);
  });
});
