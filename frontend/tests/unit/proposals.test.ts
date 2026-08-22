import { describe, expect, it } from "vitest";

import {
  buildProposalPayload,
  canAppendProposalVersion,
  currentProposalVersion,
  proposalActions,
  type Proposal,
} from "@/lib/api/proposals";

describe("proposal state affordances", () => {
  it("mirrors backend-valid role transitions", () => {
    expect(proposalActions("DRAFT", "freelancer")).toEqual(["submit"]);
    expect(proposalActions("SUBMITTED", "freelancer")).toEqual(["withdraw"]);
    expect(proposalActions("UNDER_NEGOTIATION", "freelancer")).toEqual(["withdraw"]);
    expect(proposalActions("SUBMITTED", "employer")).toEqual(["negotiate", "reject", "accept"]);
    expect(proposalActions("UNDER_NEGOTIATION", "employer")).toEqual(["reject", "accept"]);
    expect(proposalActions("ACCEPTED", "freelancer")).toEqual([]);
    expect(proposalActions("REJECTED", "employer")).toEqual([]);
  });

  it("allows append-only revisions only for freelancer-editable backend states", () => {
    expect(canAppendProposalVersion("DRAFT", "freelancer")).toBe(true);
    expect(canAppendProposalVersion("UNDER_NEGOTIATION", "freelancer")).toBe(true);
    expect(canAppendProposalVersion("SUBMITTED", "freelancer")).toBe(false);
    expect(canAppendProposalVersion("UNDER_NEGOTIATION", "employer")).toBe(false);
  });
});

describe("proposal payload", () => {
  it("uses exact integer minor units and preserves milestone arithmetic", () => {
    expect(
      buildProposalPayload(
        {
          amount: "1250.00",
          currency: "USD",
          deliveryDays: "14",
          coverLetter: "  Delivery plan with measurable milestones.  ",
          milestones: [
            { title: "Research", amount: "500.00", deliveryDays: "5" },
            { title: "Delivery", amount: "750.00", deliveryDays: "9" },
          ],
        },
        "USD",
      ),
    ).toEqual({
      amount_minor: 125000,
      currency: "USD",
      delivery_days: 14,
      cover_letter: "Delivery plan with measurable milestones.",
      milestones: [
        { title: "Research", amount_minor: 50000, delivery_days: 5 },
        { title: "Delivery", amount_minor: 75000, delivery_days: 9 },
      ],
    });
  });

  it("rejects milestone totals that do not equal the proposal amount", () => {
    expect(() =>
      buildProposalPayload(
        {
          amount: "1000.00",
          currency: "USD",
          deliveryDays: "10",
          coverLetter: "",
          milestones: [{ title: "Only milestone", amount: "900.00", deliveryDays: "10" }],
        },
        "USD",
      ),
    ).toThrow("Milestone amounts must add up exactly to the proposal amount.");
  });

  it("uses the published project currency instead of trusting editable draft currency", () => {
    expect(
      buildProposalPayload(
        {
          amount: "1000",
          currency: "EUR",
          deliveryDays: "10",
          coverLetter: "",
          milestones: [],
        },
        "USD",
      ).currency,
    ).toBe("USD");
  });
});

describe("proposal version selection", () => {
  it("selects the backend current_version rather than assuming array order", () => {
    const proposal: Proposal = {
      id: "p1",
      project_id: "project-1",
      freelancer_user_id: "freelancer-1",
      status: "UNDER_NEGOTIATION",
      current_version: 2,
      versions: [
        {
          id: "v2",
          version_number: 2,
          amount_minor: 120000,
          currency: "USD",
          delivery_days: 12,
          cover_letter: "Current",
          milestones: [],
        },
        {
          id: "v1",
          version_number: 1,
          amount_minor: 100000,
          currency: "USD",
          delivery_days: 10,
          cover_letter: "Previous",
          milestones: [],
        },
      ],
    };

    expect(currentProposalVersion(proposal).id).toBe("v2");
  });
});
