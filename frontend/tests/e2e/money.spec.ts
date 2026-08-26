import { expect, test, type Page } from "@playwright/test";

const freelancerId = "11111111-1111-4111-8111-111111111111";
const employerId = "a2111111-1111-4111-8111-111111111111";
const projectId = "c1111111-1111-4111-8111-111111111111";
const contractId = "d2111111-1111-4111-8111-111111111111";
const milestoneId = "e2111111-1111-4111-8111-111111111111";
const documentHash = "0123456789abcdef".repeat(4);

type FinancialMilestoneStatus = "CREATED" | "FUNDED" | "APPROVED" | "RELEASED";

function milestone(status: string) {
  return {
    id: milestoneId,
    contract_version_id: "f2111111-1111-4111-8111-111111111111",
    sequence: 1,
    title: "Accessible checkout delivery",
    amount_minor: 120000,
    currency: "USD",
    delivery_days: 14,
    status,
    events: [],
  };
}

function contract(milestoneStatus: string) {
  return {
    id: contractId,
    project_id: projectId,
    accepted_proposal_id: "d1111111-1111-4111-8111-111111111111",
    employer_user_id: employerId,
    freelancer_user_id: freelancerId,
    status: "ACTIVE",
    current_version: 1,
    created_at: "2026-08-22T11:00:00+00:00",
    activated_at: "2026-08-22T11:05:00+00:00",
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
          project_description: "Design and validate an accessible checkout architecture.",
          proposal_cover_letter: "I will de-risk checkout delivery and validation.",
        },
        price: { amount_minor: 120000 },
        currency: "USD",
        delivery_days: 14,
        commission: { platform_bps: 1000 },
        attachments: [],
      },
      signatures: [
        {
          id: "11111111-9999-4999-8999-999999999999",
          user_id: freelancerId,
          signed_at: "2026-08-22T11:05:00+00:00",
          document_hash: documentHash,
          signature_provider_reference: null,
        },
        {
          id: "a2111111-9999-4999-8999-999999999999",
          user_id: employerId,
          signed_at: "2026-08-22T11:05:00+00:00",
          document_hash: documentHash,
          signature_provider_reference: null,
        },
      ],
      milestones: [milestone(milestoneStatus)],
    },
  };
}

function financial(
  milestoneStatus: FinancialMilestoneStatus,
  escrowBalanceMinor: number,
  commissionBps: number | null = null,
) {
  return {
    milestone_id: milestoneId,
    milestone_status: milestoneStatus,
    contracted_amount_minor: 120000,
    currency: "USD",
    escrow_balance_minor: escrowBalanceMinor,
    commission_bps: commissionBps,
  };
}

async function signIn(page: Page, role: "freelancer" | "employer", next: string) {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email address").fill(`${role}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect(page).toHaveURL(new RegExp(next.replaceAll("/", "\\/")));
}

test("employer creates one idempotent funding request and waits for provider capture", async ({ page }) => {
  const finance = financial("CREATED", 0);
  const contractState = contract("CREATED");

  await page.route(`**/api/backend/contracts/${contractId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(contractState) }),
  );
  await page.route(`**/api/backend/milestones/${milestoneId}/financials`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(finance) }),
  );
  await page.route(`**/api/backend/milestones/${milestoneId}/fund`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({});
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        payment_intent_id: "99111111-1111-4111-8111-111111111111",
        milestone_id: milestoneId,
        provider: "sandbox",
        provider_reference: "sandbox-payment-1",
        amount_minor: 120000,
        currency: "USD",
        status: "PENDING",
      }),
    });
  });

  await signIn(page, "employer", `/dashboard/contracts/${contractId}`);
  const money = page.getByRole("region", { name: "Escrow & release" });
  await expect(money.getByText("EMPTY", { exact: true })).toBeVisible();
  await expect(money.getByText("$1,200.00", { exact: true }).first()).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await money.getByRole("button", { name: "Fund escrow" }).click();

  await expect(
    money.getByText(
      "Funding request accepted for $1,200.00. Escrow remains pending until provider capture is confirmed.",
    ),
  ).toBeVisible();
  await expect(money.getByText("AWAITING CAPTURE", { exact: true })).toBeVisible();
  await expect(money.getByRole("button", { name: "Fund escrow" })).toHaveCount(0);
  await expect(money.getByText(/Backend milestone created · escrow balance \$0\.00/i)).toBeVisible();
});

test("employer releases only fully funded approved escrow after exact confirmation", async ({ page }) => {
  let contractState = contract("APPROVED");
  let finance = financial("APPROVED", 120000, 1000);

  await page.route(`**/api/backend/contracts/${contractId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(contractState) }),
  );
  await page.route(`**/api/backend/milestones/${milestoneId}/financials`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(finance) }),
  );
  await page.route(`**/api/backend/milestones/${milestoneId}/release`, async (route) => {
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    expect(route.request().postData()).toBeNull();
    finance = financial("RELEASED", 0, 1000);
    contractState = contract("RELEASED");
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(finance) });
  });

  await signIn(page, "employer", `/dashboard/contracts/${contractId}`);
  const money = page.getByRole("region", { name: "Escrow & release" });
  await expect(money.getByRole("button", { name: "Release payment" })).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("Release $1,200.00");
    await dialog.accept();
  });
  await money.getByRole("button", { name: "Release payment" }).click();

  await expect(money.getByText("Backend confirmed release of $1,200.00.")).toBeVisible();
  await expect(money.locator('[data-status="RELEASED"]')).toBeVisible();
  await expect(money.getByText("EMPTY", { exact: true })).toBeVisible();
  await expect(money.getByRole("button", { name: "Release payment" })).toHaveCount(0);
});

test("employer can fully refund funded escrow only before work starts", async ({ page }) => {
  let contractState = contract("FUNDED");
  let finance = financial("FUNDED", 120000, 1000);

  await page.route(`**/api/backend/contracts/${contractId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(contractState) }),
  );
  await page.route(`**/api/backend/milestones/${milestoneId}/financials`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(finance) }),
  );
  await page.route(`**/api/backend/milestones/${milestoneId}/refund`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({});
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    finance = financial("CREATED", 0, 1000);
    contractState = contract("CREATED");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        refund_id: "ab111111-1111-4111-8111-111111111111",
        milestone_id: milestoneId,
        provider: "sandbox",
        provider_reference: "sandbox-refund-1",
        amount_minor: 120000,
        currency: "USD",
        status: "SUCCEEDED",
      }),
    });
  });

  await signIn(page, "employer", `/dashboard/contracts/${contractId}`);
  const money = page.getByRole("region", { name: "Escrow & release" });
  await expect(money.getByRole("button", { name: "Refund escrow" })).toBeVisible();

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("Refund the full $1,200.00 escrow");
    await dialog.accept();
  });
  await money.getByRole("button", { name: "Refund escrow" }).click();

  await expect(money.getByText("Backend confirmed the full $1,200.00 pre-work refund.")).toBeVisible();
  await expect(money.locator('[data-status="CREATED"]')).toBeVisible();
  await expect(money.getByText("EMPTY", { exact: true })).toBeVisible();
  await expect(money.getByRole("button", { name: "Refund escrow" })).toHaveCount(0);
});

test("freelancer payout re-reads ledger balance after backend success", async ({ page }) => {
  let wallet = { balances: { USD: 9000 } };

  await page.route("**/api/backend/wallet", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(wallet) }),
  );
  await page.route("**/api/backend/payouts", async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      amount_minor: 5500,
      currency: "USD",
    });
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    wallet = { balances: { USD: 3500 } };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        payout_id: "aa111111-1111-4111-8111-111111111111",
        provider: "sandbox",
        provider_reference: "sandbox-payout-1",
        amount_minor: 5500,
        currency: "USD",
        status: "SUCCEEDED",
      }),
    });
  });

  await signIn(page, "freelancer", "/dashboard/wallet");
  await expect(page.getByRole("heading", { level: 1, name: "Wallet & payouts" })).toBeVisible();
  await expect(page.getByText("$90.00", { exact: true })).toBeVisible();
  await page.getByLabel("Payout amount").fill("55.00");

  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("$55.00 payout");
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Review payout request" }).click();

  await expect(page.getByText("Backend confirmed $55.00 payout status succeeded.")).toBeVisible();
  await expect(page.getByText("$35.00", { exact: true })).toBeVisible();
  await expect(page.getByText("sandbox-payout-1", { exact: true })).toBeVisible();
});
