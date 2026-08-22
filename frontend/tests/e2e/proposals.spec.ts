import { expect, test, type Page } from "@playwright/test";

const projectId = "c1111111-1111-4111-8111-111111111111";
const freelancerId = "11111111-1111-4111-8111-111111111111";
const proposalId = "d1111111-1111-4111-8111-111111111111";

function proposal(status: string, version = 1) {
  return {
    id: proposalId,
    project_id: projectId,
    freelancer_user_id: freelancerId,
    status,
    current_version: version,
    versions: Array.from({ length: version }, (_, index) => ({
      id: `e${index + 1}111111-1111-4111-8111-111111111111`,
      version_number: index + 1,
      amount_minor: index === 0 ? 1200000 : 1150000,
      currency: "USD",
      delivery_days: index === 0 ? 14 : 12,
      cover_letter:
        index === 0
          ? "I will de-risk the checkout through research, architecture, and accessible validation."
          : "Updated delivery plan after employer negotiation request.",
      milestones: [
        {
          id: `f${index + 1}111111-1111-4111-8111-111111111111`,
          sequence: 1,
          title: "Research and architecture",
          amount_minor: index === 0 ? 1200000 : 1150000,
          delivery_days: index === 0 ? 14 : 12,
        },
      ],
    })),
  };
}

async function signIn(page: Page, role: "freelancer" | "employer", next: string) {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email address").fill(`${role}@example.com`);
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect(page).toHaveURL(new RegExp(next.replaceAll("/", "\\/")));
}

test("freelancer creates a draft then submits through backend-confirmed transition", async ({ page }) => {
  let state = proposal("DRAFT");

  await page.route(`**/api/backend/projects/${projectId}/proposals`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const body = route.request().postDataJSON();
    expect(body.amount_minor).toBe(1200000);
    expect(body.currency).toBe("USD");
    expect(body.milestones).toHaveLength(1);
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(state) });
  });
  await page.route(`**/api/backend/proposals/${proposalId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) }),
  );
  await page.route(`**/api/backend/proposals/${proposalId}/submit`, async (route) => {
    state = proposal("SUBMITTED");
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) });
  });

  await signIn(page, "freelancer", `/projects/${projectId}/proposal`);
  await expect(page.getByRole("heading", { name: "Propose a clear delivery plan." })).toBeVisible();
  await page.getByLabel("Proposal amount").fill("12000");
  await page.getByLabel("Delivery days").fill("14");
  await page.getByLabel("Cover letter").fill(
    "I will de-risk the checkout through research, architecture, and accessible validation.",
  );
  await page.getByRole("button", { name: "+ Add milestone" }).click();
  await page.getByLabel("Title", { exact: true }).fill("Research and architecture");
  await page.getByLabel("Amount", { exact: true }).fill("12000");
  await page.getByLabel("Days", { exact: true }).fill("14");
  await page.getByRole("button", { name: "Save proposal draft" }).click();

  await expect(page).toHaveURL(new RegExp(`/dashboard/proposals/${proposalId}$`));
  await expect(page.getByText("DRAFT", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit to employer" })).toBeVisible();
  await page.getByRole("button", { name: "Submit to employer" }).click();
  await expect(page.getByText("SUBMITTED", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Withdraw proposal" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Append version/i })).toHaveCount(0);
});

test("employer compares submitted proposals and requests negotiation", async ({ page }) => {
  let state = proposal("SUBMITTED");

  await page.route(`**/api/backend/projects/${projectId}/proposals`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [state] }),
    }),
  );
  await page.route(`**/api/backend/proposals/${proposalId}/negotiate`, async (route) => {
    state = proposal("UNDER_NEGOTIATION");
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(state) });
  });

  await signIn(page, "employer", `/dashboard/projects/${projectId}/proposals`);
  await expect(page.getByRole("heading", { name: "Rebuild a cross-market checkout" })).toBeVisible();
  await expect(page.getByText("SUBMITTED", { exact: true })).toBeVisible();
  await expect(page.getByText("$12,000.00")).toBeVisible();
  await expect(page.getByRole("button", { name: "Negotiate" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Accept" })).toBeVisible();
  await page.getByRole("button", { name: "Negotiate" }).click();
  await expect(page.getByText("UNDER NEGOTIATION", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Negotiate" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Accept" })).toBeVisible();
});
