import { describe, expect, it, vi } from "vitest";

import {
  canOfferFinancialAction,
  financialActionAmount,
  getPaymentAction,
  mutateMilestoneFinancials,
  requestPayout,
  type MilestoneFinancialState,
} from "@/lib/api/money";

vi.mock("@/lib/api/product-client", () => ({
  productJson: vi.fn(async () => ({ ok: true })),
}));

import { productJson } from "@/lib/api/product-client";

function financial(overrides: Partial<MilestoneFinancialState> = {}): MilestoneFinancialState {
  return {
    milestone_id: "11111111-1111-4111-8111-111111111111",
    milestone_status: "CREATED",
    contracted_amount_minor: 120000,
    currency: "USD",
    escrow_balance_minor: 0,
    commission_bps: null,
    ...overrides,
  };
}

describe("money affordances", () => {
  it("offers funding only to the active employer when the authoritative created escrow is empty", () => {
    const state = financial();
    expect(
      canOfferFinancialAction({
        action: "fund",
        role: "employer",
        contractStatus: "ACTIVE",
        milestoneStatus: "CREATED",
        financial: state,
      }),
    ).toBe(true);
    expect(
      canOfferFinancialAction({
        action: "fund",
        role: "freelancer",
        contractStatus: "ACTIVE",
        milestoneStatus: "CREATED",
        financial: state,
      }),
    ).toBe(false);
    expect(
      canOfferFinancialAction({
        action: "fund",
        role: "employer",
        contractStatus: "ACTIVE",
        milestoneStatus: "CREATED",
        financial: financial({ escrow_balance_minor: 1 }),
      }),
    ).toBe(false);
  });

  it("hides money controls when the contract view and financial projection disagree", () => {
    expect(
      canOfferFinancialAction({
        action: "fund",
        role: "employer",
        contractStatus: "ACTIVE",
        milestoneStatus: "CREATED",
        financial: financial({ milestone_status: "FUNDED", escrow_balance_minor: 120000 }),
      }),
    ).toBe(false);
  });

  it("offers full pre-work refund only for a fully funded FUNDED milestone", () => {
    const funded = financial({
      milestone_status: "FUNDED",
      escrow_balance_minor: 120000,
      commission_bps: 1000,
    });
    expect(
      canOfferFinancialAction({
        action: "refund",
        role: "employer",
        contractStatus: "ACTIVE",
        milestoneStatus: "FUNDED",
        financial: funded,
      }),
    ).toBe(true);
    expect(
      canOfferFinancialAction({
        action: "refund",
        role: "employer",
        contractStatus: "ACTIVE",
        milestoneStatus: "FUNDED",
        financial: { ...funded, escrow_balance_minor: 119999 },
      }),
    ).toBe(false);
  });

  it("offers release only for a fully funded APPROVED milestone", () => {
    const approved = financial({
      milestone_status: "APPROVED",
      escrow_balance_minor: 120000,
      commission_bps: 1000,
    });
    expect(
      canOfferFinancialAction({
        action: "release",
        role: "employer",
        contractStatus: "ACTIVE",
        milestoneStatus: "APPROVED",
        financial: approved,
      }),
    ).toBe(true);
    expect(
      canOfferFinancialAction({
        action: "release",
        role: "employer",
        contractStatus: "ACTIVE",
        milestoneStatus: "APPROVED",
        financial: { ...approved, escrow_balance_minor: 119999 },
      }),
    ).toBe(false);
  });

  it("uses only the backend escrow balance for the full-refund confirmation amount", () => {
    expect(
      financialActionAmount(
        "refund",
        financial({ milestone_status: "FUNDED", escrow_balance_minor: 120000 }),
      ),
    ).toBe(120000);
  });
});

describe("money mutations", () => {
  it("lets the backend choose the payment provider when no public override is configured", async () => {
    await mutateMilestoneFinancials("milestone-1", "fund", "fund-key");
    expect(productJson).toHaveBeenLastCalledWith("milestones/milestone-1/fund", {
      method: "POST",
      headers: { "Idempotency-Key": "fund-key" },
      body: JSON.stringify({}),
    });

    await mutateMilestoneFinancials("milestone-1", "refund", "refund-key");
    expect(productJson).toHaveBeenLastCalledWith("milestones/milestone-1/refund", {
      method: "POST",
      headers: { "Idempotency-Key": "refund-key" },
      body: JSON.stringify({}),
    });
  });

  it("does not invent a provider body for release", async () => {
    await mutateMilestoneFinancials("milestone-1", "release", "release-key");
    expect(productJson).toHaveBeenLastCalledWith("milestones/milestone-1/release", {
      method: "POST",
      headers: { "Idempotency-Key": "release-key" },
      body: undefined,
    });
  });

  it("retrieves the provider action through the authenticated payment-intent route", async () => {
    await getPaymentAction("payment-intent-1");
    expect(productJson).toHaveBeenLastCalledWith("payment-intents/payment-intent-1/action");
  });

  it("posts payout amount/currency without mutating any local balance", async () => {
    await requestPayout({ amountMinor: 5500, currency: "USD", idempotencyKey: "payout-key" });
    expect(productJson).toHaveBeenLastCalledWith("payouts", {
      method: "POST",
      headers: { "Idempotency-Key": "payout-key" },
      body: JSON.stringify({
        amount_minor: 5500,
        currency: "USD",
      }),
    });
  });
});
