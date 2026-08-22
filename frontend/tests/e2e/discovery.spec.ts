import { expect, test } from "@playwright/test";

const freelancerId = "11111111-1111-4111-8111-111111111111";

test("talent discovery renders backend projection facts and URL filters", async ({ page }) => {
  await page.goto("/talent");
  await expect(page.getByRole("heading", { name: /Find the right expertise/i })).toBeVisible();
  await expect(page.getByRole("link", { name: "Product systems designer" })).toBeVisible();
  await expect(page.getByText("18 completed jobs")).toBeVisible();
  await page.getByLabel("What do you need?").fill("no-match");
  await page.getByRole("button", { name: "Search talent" }).click();
  await expect(page).toHaveURL(/q=no-match/);
  await expect(page.getByText(/No profiles match these filters yet/i)).toBeVisible();
});

test("public freelancer profile exposes portfolio, schedule, and reviews", async ({ page }) => {
  await page.goto(`/talent/${freelancerId}`);
  await expect(page.getByRole("heading", { name: "Product systems designer" })).toBeVisible();
  await expect(page.getByText("Global banking design system")).toBeVisible();
  await expect(page.getByText("Clear thinking, precise delivery, and excellent communication.")).toBeVisible();
  await expect(page.getByText("09:00–17:00")).toBeVisible();
});

test("freelancer can authenticate through the BFF and save profile-owned data", async ({ page }) => {
  await page.goto("/login?next=/dashboard/profile");
  await page.getByLabel("Email address").fill("freelancer@example.com");
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect(page).toHaveURL(/\/dashboard\/profile$/);
  await expect(page.getByRole("heading", { name: /Shape the profile employers evaluate/i })).toBeVisible();

  await page.getByLabel("Professional title").fill("Principal product systems designer");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText("Professional profile saved.")).toBeVisible();

  await page.getByRole("button", { name: "Save weekly schedule" }).click();
  await expect(page.getByText("Weekly availability saved.")).toBeVisible();

  const portfolioForm = page.locator("form").filter({ has: page.getByRole("button", { name: "Add portfolio item" }) });
  await portfolioForm.getByLabel("Title").fill("Checkout architecture redesign");
  await portfolioForm.getByRole("button", { name: "Add portfolio item" }).click();
  await expect(page.getByText("Checkout architecture redesign")).toBeVisible();
  await expect(page.getByText("Portfolio item published.")).toBeVisible();
});
