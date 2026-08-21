import { expect, test } from "@playwright/test";

const USER_ID = "11111111-1111-4111-8111-111111111111";

test("talent discovery renders backend search projection data", async ({ page }) => {
  await page.goto("/talent");
  await expect(page.getByRole("heading", { name: /Find the right expertise/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Platform & API Engineer" })).toBeVisible();
  await expect(page.getByText("$145.00 / hour")).toBeVisible();
  await expect(page.getByText("18 completed jobs")).toBeVisible();
  await expect(page.getByText("Accepting work").first()).toBeVisible();
});

test("talent filters become URL-addressable repeated backend filters", async ({ page }) => {
  await page.goto("/talent");
  await page.getByLabel("Search expertise").fill("platform engineer");
  await page.getByLabel("Skills").fill("Python, PostgreSQL");
  await page.getByLabel("Availability").selectOption("true");
  await page.getByRole("button", { name: "Search talent" }).click();

  await expect(page).toHaveURL(/q=platform\+engineer/);
  const url = new URL(page.url());
  expect(url.searchParams.getAll("skill")).toEqual(["Python", "PostgreSQL"]);
  expect(url.searchParams.get("available")).toBe("true");
  await expect(page.getByRole("heading", { name: "Platform & API Engineer" })).toBeVisible();
});

test("public profile combines profile, SAFE portfolio metadata, and reviews", async ({ page }) => {
  await page.goto(`/talent/${USER_ID}`);
  await expect(page.getByRole("heading", { name: "Platform & API Engineer" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Expertise" })).toBeVisible();
  await expect(page.getByText("distributed-systems")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Portfolio" })).toBeVisible();
  await expect(page.getByText("Marketplace reliability program")).toBeVisible();
  await expect(page.getByText("1 safe file")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Client reviews" })).toBeVisible();
  await expect(page.getByText(/Clear architecture/)).toBeVisible();
});
