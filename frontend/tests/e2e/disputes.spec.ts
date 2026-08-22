import { expect, test, type Page } from "@playwright/test";

import type { Contract } from "@/lib/api/contracts";
import type { DisputeCase, DisputeStatus } from "@/lib/api/disputes";

const employerId = "11111111-1111-4111-8111-111111111111";
const freelancerId = "22222222-2222-4222-8222-222222222222";
const adminId = "33333333-3333-4333-8333-333333333333";
const contractId = "44444444-4444-4444-8444-444444444444";
const milestoneId = "55555555-5555-4555-8555-555555555555";
const disputeId = "66666666-6666-4666-8666-666666666666";

function contract(): Contract {
  return {
    id: contractId,
    project_id: "88888888-8888-4888-8888-888888888888",
    accepted_proposal_id: "99999999-9999-4999-8999-999999999999",
    employer_user_id: employerId,
    freelancer_user_id: freelancerId,
    status: "ACTIVE",
    current_version: 1,
    created_at: "2026-08-22T12:00:00Z",
    activated_at: "2026-08-22T12:05:00Z",
    cancelled_at: null,
    parties: [
      { user_id: employerId, role: "EMPLOYER", required_signature: true },
      { user_id: freelancerId, role: "FREELANCER", required_signature: true },
    ],
    version: {
      id: "77777777-7777-4777-8777-777777777777",
      version_number: 1,
      document_hash: "a".repeat(64),
      snapshot: { scope: { project_title: "Dispute project" }, currency: "USD" },
      created_at: "2026-08-22T12:00:00Z",
      signatures: [],
      milestones: [
        {
          id: milestoneId,
          contract_version_id: "77777777-7777-4777-8777-777777777777",
          sequence: 1,
          title: "Final delivery",
          amount_minor: 10000,
          currency: "USD",
          delivery_days: 5,
          status: "APPROVED",
          events: [],
        },
      ],
    },
  };
}

function openCase(status: DisputeStatus = "OPEN"): DisputeCase {
  return {
    id: disputeId,
    milestone_id: milestoneId,
    contract_id: contractId,
    opened_by_user_id: employerId,
    status,
    reason: "Delivered scope differs from the signed contract.",
    created_at: "2026-08-22T12:10:00Z",
    resolved_at: null,
    parties: [
      { user_id: employerId, role: "EMPLOYER" },
      { user_id: freelancerId, role: "FREELANCER" },
    ],
    evidence: [],
    events: [
      {
        event_type: "OPENED",
        from_status: null,
        to_status: "OPEN",
        reason: "Delivered scope differs from the signed contract.",
        created_at: "2026-08-22T12:10:00Z",
      },
    ],
    decision: null,
    milestone: {
      id: milestoneId,
      sequence: 1,
      title: "Final delivery",
      amount_minor: 10000,
      currency: "USD",
      status: "DISPUTED",
    },
  };
}

async function routeSession(page: Page, role: "employer" | "admin") {
  const user =
    role === "admin"
      ? { id: adminId, email: "admin@example.com", roles: ["admin"] }
      : { id: employerId, email: "employer@example.com", roles: ["employer"] };
  await page.route("**/api/session/me", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(user) }),
  );
}

async function routeInbox(page: Page, cases: DisputeCase[]) {
  await page.route("**/api/backend/disputes?*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: cases, next_after: null }),
    }),
  );
}

test("contract party opens a dispute and receives backend-frozen case state", async ({ page }) => {
  await routeSession(page, "employer");
  await routeInbox(page, []);
  await page.route(`**/api/backend/contracts/${contractId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(contract()) }),
  );

  const currentCase = openCase();
  await page.route(`**/api/backend/milestones/${milestoneId}/disputes`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      reason: "The approved delivery is missing agreed source files.",
    });
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(currentCase),
    });
  });
  await page.route(`**/api/backend/disputes/${disputeId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentCase) }),
  );
  page.on("dialog", (dialog) => void dialog.accept());

  await page.goto(`/dashboard/disputes?contract=${contractId}`);
  await expect(page.getByRole("heading", { name: "Dispute resolution" })).toBeVisible();
  await page.getByLabel("Milestone", { exact: true }).selectOption(milestoneId);
  await page
    .getByLabel("Reason for dispute", { exact: true })
    .fill("The approved delivery is missing agreed source files.");
  await page.getByRole("button", { name: "Open dispute and freeze release" }).click();

  await expect(
    page.getByText("Dispute opened. Milestone release is frozen by backend state."),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "Dispute case detail" })
      .locator('strong[data-status="OPEN"]'),
  ).toBeVisible();
  await expect(page.getByText("$100.00")).toBeVisible();
});

test("scanning evidence is never attached before SAFE authorization", async ({ page }) => {
  await routeSession(page, "employer");
  const dispute = openCase("EVIDENCE_COLLECTION");
  await routeInbox(page, [dispute]);
  await page.route(`**/api/backend/disputes/${disputeId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(dispute) }),
  );
  await page.route("**/api/backend/files/uploads", (route) =>
    route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify({
        file: {
          id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          original_name: "proof.pdf",
          mime_type: "application/pdf",
          size_bytes: 5,
          sha256: null,
          purpose: "DISPUTE_EVIDENCE",
          status: "QUARANTINED",
          rejection_reason: null,
          created_at: "2026-08-22T12:20:00Z",
        },
        upload_url: "http://127.0.0.1:3000/evidence-upload/mock",
      }),
    }),
  );
  await page.route("**/evidence-upload/mock", (route) => route.fulfill({ status: 200, body: "" }));
  await page.route(
    "**/api/backend/files/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/complete",
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          original_name: "proof.pdf",
          mime_type: "application/pdf",
          size_bytes: 5,
          sha256: "b".repeat(64),
          purpose: "DISPUTE_EVIDENCE",
          status: "SCANNING",
          rejection_reason: null,
          created_at: "2026-08-22T12:20:00Z",
        }),
      }),
  );
  let attachCalls = 0;
  await page.route(`**/api/backend/disputes/${disputeId}/evidence`, (route) => {
    attachCalls += 1;
    return route.fulfill({ status: 500, body: "{}" });
  });

  await page.goto("/dashboard/disputes");
  await page.getByLabel("Evidence file", { exact: true }).setInputFiles({
    name: "proof.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("proof"),
  });
  await page.getByLabel("Evidence note", { exact: true }).fill("Shows the submitted archive contents.");
  await page.getByRole("button", { name: "Upload evidence" }).click();

  await expect(page.getByText("Attachment remains blocked until SAFE.")).toBeVisible();
  await expect(page.getByText("SCANNING", { exact: true })).toBeVisible();
  expect(attachCalls).toBe(0);
});

test("administrator blocks invalid split and resolves exact funded allocation idempotently", async ({
  page,
}) => {
  await routeSession(page, "admin");
  let currentCase = openCase("UNDER_REVIEW");
  currentCase.events.push({
    event_type: "ADMIN_TRANSITION",
    from_status: "EVIDENCE_COLLECTION",
    to_status: "UNDER_REVIEW",
    reason: "Evidence window complete.",
    created_at: "2026-08-22T12:30:00Z",
  });
  await routeInbox(page, [currentCase]);
  await page.route(`**/api/backend/disputes/${disputeId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentCase) }),
  );

  let resolveCalls = 0;
  await page.route(`**/api/backend/disputes/${disputeId}/resolve`, async (route) => {
    resolveCalls += 1;
    expect(route.request().postDataJSON()).toEqual({
      outcome: "SPLIT",
      reason: "Evidence supports a sixty-forty allocation.",
      freelancer_award_minor: 6000,
      client_refund_minor: 4000,
    });
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    currentCase = {
      ...currentCase,
      status: "RESOLVED",
      resolved_at: "2026-08-22T12:40:00Z",
      decision: {
        id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        administrator_user_id: adminId,
        outcome: "SPLIT",
        freelancer_award_minor: 6000,
        freelancer_net_minor: 5400,
        client_refund_minor: 4000,
        commission_minor: 600,
        currency: "USD",
        journal_transaction_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        refund_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        reason: "Evidence supports a sixty-forty allocation.",
        created_at: "2026-08-22T12:40:00Z",
      },
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(currentCase),
    });
  });
  page.on("dialog", (dialog) => void dialog.accept());

  await page.goto("/dashboard/disputes");
  await page.getByLabel("Audit reason", { exact: true }).fill("Evidence supports a sixty-forty allocation.");
  await page.getByLabel("Outcome", { exact: true }).selectOption("SPLIT");
  await page.getByLabel("Freelancer award (USD)", { exact: true }).fill("60.00");
  await page.getByLabel("Client refund (USD)", { exact: true }).fill("30.00");
  await page.getByRole("button", { name: "Resolve dispute" }).click();
  await expect(page.getByText("Split must equal exactly $100.00.", { exact: true })).toBeVisible();
  expect(resolveCalls).toBe(0);

  await page.getByLabel("Client refund (USD)", { exact: true }).fill("40.00");
  await page.getByRole("button", { name: "Resolve dispute" }).click();
  await expect(page.getByRole("heading", { name: "Final decision" })).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Dispute case detail" }).getByText("SPLIT", { exact: true }),
  ).toBeVisible();
  expect(resolveCalls).toBe(1);
});
