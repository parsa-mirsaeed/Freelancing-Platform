import { expect, test } from "@playwright/test";

const USER_ID = "11111111-1111-4111-8111-111111111111";

const profile = {
  id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  user_id: USER_ID,
  title: "Platform & API Engineer",
  bio: "Reliable marketplace systems.",
  hourly_rate_minor: 14500,
  currency: "USD",
  timezone: "Europe/Zurich",
  accepting_work: true,
  languages: ["English", "German"],
  skills: ["python", "postgresql"],
  projection_version: 7,
  availability: {
    rules: [
      { id: "r1", weekday: 0, start_time: "09:00", end_time: "17:00", timezone: "Europe/Zurich" },
    ],
    exceptions: [],
  },
};

test("freelancer edits profile through the same-origin BFF", async ({ page }) => {
  await page.route("**/api/session/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: USER_ID, email: "freelancer@example.com", roles: ["freelancer"] }),
    });
  });
  await page.route("**/api/backend/freelancers/me/profile", async (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      expect(body.title).toBe("Principal Platform Engineer");
      expect(body.hourly_rate_minor).toBe(15050);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ...profile, ...body, title: body.title, hourly_rate_minor: body.hourly_rate_minor }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(profile) });
  });
  await page.route(`**/api/backend/freelancers/${USER_ID}/portfolio`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [] }) });
  });

  await page.goto("/dashboard/profile");
  await expect(page.getByRole("heading", { name: "Professional profile" })).toBeVisible();
  await expect(page.getByLabel("Professional title")).toHaveValue("Platform & API Engineer");
  await page.getByLabel("Professional title").fill("Principal Platform Engineer");
  await page.getByLabel("Hourly rate").fill("150.50");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText("Professional profile saved.")).toBeVisible();
});

test("employer account does not receive freelancer editing controls", async ({ page }) => {
  await page.route("**/api/session/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: USER_ID, email: "employer@example.com", roles: ["employer"] }),
    });
  });

  await page.goto("/dashboard/profile");
  await expect(page.getByRole("heading", { name: "Freelancer profile studio" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Browse talent" })).toBeVisible();
  await expect(page.getByLabel("Professional title")).toHaveCount(0);
});
