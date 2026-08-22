import { expect, test, type Page } from "@playwright/test";

const freelancerId = "11111111-1111-4111-8111-111111111111";
const employerId = "a2111111-1111-4111-8111-111111111111";
const projectId = "c1111111-1111-4111-8111-111111111111";
const contractId = "d2111111-1111-4111-8111-111111111111";
const milestoneId = "e2111111-1111-4111-8111-111111111111";
const documentHash = "0123456789abcdef".repeat(4);

function milestone(status: string, events: object[] = []) {
  return {
    id: milestoneId,
    contract_version_id: "f2111111-1111-4111-8111-111111111111",
    sequence: 1,
    title: "Accessible checkout delivery",
    amount_minor: 1200000,
    currency: "USD",
    delivery_days: 14,
    status,
    events,
  };
}

function contract({
  status = "PENDING_SIGNATURES",
  signatures = [],
  milestoneStatus = "CREATED",
  events = [],
}: {
  status?: string;
  signatures?: object[];
  milestoneStatus?: string;
  events?: object[];
} = {}) {
  return {
    id: contractId,
    project_id: projectId,
    accepted_proposal_id: "d1111111-1111-4111-8111-111111111111",
    employer_user_id: employerId,
    freelancer_user_id: freelancerId,
    status,
    current_version: 1,
    created_at: "2026-08-22T11:00:00+00:00",
    activated_at: status === "ACTIVE" ? "2026-08-22T11:05:00+00:00" : null,
    cancelled_at: null,
    parties: [
      { user_id: employerId, role: "EMPLOYER", required_signature: true },
      { user_id: freelancerId, role: "FREELANCER", required_signature: true },
    ],
    version: {
      id: "f2111111-1111-4111-8111-111111111111",
      version_number: 1,
      document_hash: documentHash,
      created_at: "2026-08-22T11:00:00+00:00",
      snapshot: {
        schema_version: 2,
        source: { project_id: projectId, proposal_version: 1 },
        scope: {
          project_title: "Rebuild a cross-market checkout",
          project_description:
            "Design and validate a checkout architecture that works across multiple regulatory markets.",
          proposal_cover_letter:
            "I will de-risk the checkout through research, architecture, and accessible validation.",
        },
        price: { amount_minor: 1200000 },
        currency: "USD",
        delivery_days: 14,
        commission: { platform_bps: 1000 },
        attachments: [],
      },
      signatures,
      milestones: [milestone(milestoneStatus, events)],
    },
  };
}

function onlyMilestone(state: ReturnType<typeof contract>) {
  const item = state.version.milestones[0];
  if (!item) throw new Error("Contract fixture must include a milestone.");
  return item;
}

async function signIn(page: Page, role: "freelancer" | "employer", next: string) {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email address").fill(`${role}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect(page).toHaveURL(new RegExp(next.replaceAll("/", "\\/")));
}

function signature(userId: string) {
  return {
    id: `${userId.slice(0, 8)}-9999-4999-8999-999999999999`,
    user_id: userId,
    signed_at: "2026-08-22T11:05:00+00:00",
    document_hash: documentHash,
    signature_provider_reference: null,
  };
}

test("freelancer signs the exact backend document hash with an idempotency key", async ({ page }) => {
  let state = contract();

  await page.route(`**/api/backend/contracts/${contractId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }),
  );
  await page.route(`**/api/backend/contracts/${contractId}/sign`, async (route) => {
    const requestBody = route.request().postDataJSON();
    expect(requestBody).toEqual({ document_hash: documentHash });
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    state = contract({ signatures: [signature(freelancerId)] });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) });
  });

  await signIn(page, "freelancer", `/dashboard/contracts/${contractId}`);
  await expect(
    page.getByRole("heading", { level: 1, name: "Rebuild a cross-market checkout" }),
  ).toBeVisible();
  await expect(page.getByText("PENDING SIGNATURES", { exact: true })).toBeVisible();
  await expect(page.getByText("0 of 2 required signatures recorded.")).toBeVisible();
  await expect(page.getByText("0123456789ab…456789abcdef")).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Sign version 1" }).click();

  await expect(page.getByText("Your signature is recorded for this version.")).toBeVisible();
  await expect(page.getByText("Signature recorded against the current immutable document.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign version 1" })).toHaveCount(0);
});

test("freelancer starts a funded milestone and submits durable work progress", async ({ page }) => {
  let state = contract({
    status: "ACTIVE",
    signatures: [signature(freelancerId), signature(employerId)],
    milestoneStatus: "FUNDED",
  });

  await page.route(`**/api/backend/projects/${projectId}/contract`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }),
  );
  await page.route(`**/api/backend/milestones/${milestoneId}/start`, async (route) => {
    const event = {
      id: "91111111-1111-4111-8111-111111111111",
      actor_user_id: freelancerId,
      from_status: "FUNDED",
      to_status: "IN_PROGRESS",
      note: "",
      created_at: "2026-08-22T11:10:00+00:00",
    };
    const nextMilestone = milestone("IN_PROGRESS", [event]);
    state = { ...state, version: { ...state.version, milestones: [nextMilestone] } };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(nextMilestone) });
  });
  await page.route(`**/api/backend/milestones/${milestoneId}/submit`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({ note: "Checkout flow and accessibility evidence attached." });
    const events = [
      ...onlyMilestone(state).events,
      {
        id: "92111111-1111-4111-8111-111111111111",
        actor_user_id: freelancerId,
        from_status: "IN_PROGRESS",
        to_status: "SUBMITTED",
        note: "Checkout flow and accessibility evidence attached.",
        created_at: "2026-08-22T11:20:00+00:00",
      },
    ];
    const nextMilestone = milestone("SUBMITTED", events);
    state = { ...state, version: { ...state.version, milestones: [nextMilestone] } };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(nextMilestone) });
  });

  await signIn(page, "freelancer", `/dashboard/projects/${projectId}/contract`);
  await expect(page.locator('[data-status="FUNDED"]')).toBeVisible();
  await page.getByRole("button", { name: "Start work" }).click();
  await expect(page.locator('[data-status="IN_PROGRESS"]')).toBeVisible();
  await page.getByLabel("Submission note (optional)").fill("Checkout flow and accessibility evidence attached.");
  await page.getByRole("button", { name: "Submit work" }).click();
  await expect(page.locator('[data-status="SUBMITTED"]')).toBeVisible();
  await expect(page.getByText("Checkout flow and accessibility evidence attached.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit work" })).toHaveCount(0);
});

test("employer requests changes only with an explicit note", async ({ page }) => {
  let state = contract({
    status: "ACTIVE",
    signatures: [signature(freelancerId), signature(employerId)],
    milestoneStatus: "SUBMITTED",
    events: [
      {
        id: "93111111-1111-4111-8111-111111111111",
        actor_user_id: freelancerId,
        from_status: "IN_PROGRESS",
        to_status: "SUBMITTED",
        note: "Initial delivery ready for review.",
        created_at: "2026-08-22T11:20:00+00:00",
      },
    ],
  });

  await page.route(`**/api/backend/contracts/${contractId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }),
  );
  await page.route(`**/api/backend/milestones/${milestoneId}/request-changes`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      note: "Please add the keyboard-only checkout evidence before approval.",
    });
    const nextMilestone = milestone("CHANGES_REQUESTED", [
      ...onlyMilestone(state).events,
      {
        id: "94111111-1111-4111-8111-111111111111",
        actor_user_id: employerId,
        from_status: "SUBMITTED",
        to_status: "CHANGES_REQUESTED",
        note: "Please add the keyboard-only checkout evidence before approval.",
        created_at: "2026-08-22T11:30:00+00:00",
      },
    ]);
    state = { ...state, version: { ...state.version, milestones: [nextMilestone] } };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(nextMilestone) });
  });

  await signIn(page, "employer", `/dashboard/contracts/${contractId}`);
  await expect(page.getByRole("button", { name: "Request changes" })).toBeVisible();
  await page.getByRole("button", { name: "Request changes" }).click();
  await expect(
    page.getByText("A clear change-request note is required before requesting changes.", { exact: true }),
  ).toBeVisible();

  await page.getByLabel("Change request note").fill(
    "Please add the keyboard-only checkout evidence before approval.",
  );
  await page.getByRole("button", { name: "Request changes" }).click();
  await expect(page.locator('[data-status="CHANGES_REQUESTED"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve work" })).toHaveCount(0);
  await expect(page.getByText("Please add the keyboard-only checkout evidence before approval.")).toBeVisible();
});
