import { expect, test } from "@playwright/test";

test("public landing renders the marketplace system", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Freelancing Platform/);
  await expect(page.getByRole("heading", { name: /Hire expertise/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: /One continuous workflow/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /Start hiring/i })).toBeVisible();
});

test("sign-in navigation exposes the secure auth form", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in" }).first().click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Welcome back." })).toBeVisible();
  await expect(page.getByLabel("Email address")).toBeVisible();
  await expect(page.getByLabel("Password")).toBeVisible();
});
