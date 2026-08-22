import { expect, test } from "@playwright/test";

const gigId = "b1111111-1111-4111-8111-111111111111";
const projectId = "c1111111-1111-4111-8111-111111111111";

test("public services and projects render backend commercial facts", async ({ page }) => {
  await page.goto("/services");
  await expect(page.getByRole("heading", { name: /Buy a defined service/i })).toBeVisible();
  await expect(page.getByRole("link", { name: "Design an accessible product system" })).toBeVisible();
  await page.goto(`/services/${gigId}`);
  await expect(page.getByText("BASIC")).toBeVisible();
  await expect(page.getByText("7 days")).toBeVisible();
  await expect(page.getByText("Share product goals and existing research.")).toBeVisible();

  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: /Find serious project briefs/i })).toBeVisible();
  await expect(page.getByRole("link", { name: "Rebuild a cross-market checkout" })).toBeVisible();
  await page.goto(`/projects/${projectId}`);
  await expect(page.getByText("Product Design")).toBeVisible();
  await expect(page.getByText(/Final milestones, delivery terms, and price/i)).toBeVisible();
});

test("freelancer publishes a package service through the BFF", async ({ page }) => {
  await page.goto("/login?next=/dashboard/gigs");
  await page.getByLabel("Email address").fill("freelancer@example.com");
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect(page).toHaveURL(/\/dashboard\/gigs$/);
  await expect(page.getByRole("heading", { name: /Package expertise/i })).toBeVisible();

  await page.getByLabel("Service title").fill("Audit a design system for accessibility");
  await page.getByLabel("Description", { exact: true }).fill("A structured accessibility and interaction audit with prioritized findings.");
  await page.getByLabel("Price").fill("950");
  await page.getByRole("button", { name: "Publish service" }).click();
  await expect(page.getByText("Service published.")).toBeVisible();
  await expect(
    page
      .getByRole("heading", {
        name: "Audit a design system for accessibility",
        exact: true,
      })
      .first(),
  ).toBeVisible();
});

test("employer publishes and closes an open project only after backend confirmation", async ({ page }) => {
  await page.goto("/login?next=/dashboard/projects");
  await page.getByLabel("Email address").fill("employer@example.com");
  await page.getByLabel("Password").fill("correct-horse-battery-staple");
  await page.getByRole("button", { name: "Sign in securely" }).click();
  await expect(page).toHaveURL(/\/dashboard\/projects$/);
  await expect(page.getByRole("heading", { name: /Publish a brief/i })).toBeVisible();

  await page.getByLabel("Project title").fill("Design a global freelancer onboarding flow");
  await page.getByLabel("Description", { exact: true }).fill("Create a multilingual onboarding experience with clear identity and portfolio steps.");
  await page.getByLabel(/Skills/).fill("Product Design, Research");
  await page.getByLabel("Minimum").fill("5000");
  await page.getByLabel("Maximum").fill("9000");
  await page.getByLabel("Currency").fill("USD");
  await page.getByRole("button", { name: "Publish project" }).click();
  await expect(page.getByText("Project published.")).toBeVisible();
  await expect(page.getByText("Design a global freelancer onboarding flow")).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("article").filter({ hasText: "Design a global freelancer onboarding flow" }).getByRole("button", { name: "Close" }).click();
  await expect(page.getByText("Project closed after backend completion checks passed.")).toBeVisible();
});
