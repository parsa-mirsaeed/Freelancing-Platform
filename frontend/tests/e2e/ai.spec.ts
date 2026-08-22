import { expect, test, type Page } from "@playwright/test";

const employerId = "a2111111-1111-4111-8111-111111111111";
const freelancerId = "11111111-1111-4111-8111-111111111111";
const projectId = "c1111111-1111-4111-8111-111111111111";
const candidateId = "22222222-2222-4222-8222-222222222222";
const runId = "33333333-3333-4333-8333-333333333333";

async function routeSession(page: Page, roles: string[], userId: string) {
  await page.route("**/api/session/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: userId, email: "ai-user@example.com", roles }),
    }),
  );
}

test("employer sees explainable matching, version metadata, and interval pricing", async ({ page }) => {
  await routeSession(page, ["employer"], employerId);
  const eventTypes: string[] = [];
  await page.route("**/api/backend/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/backend/projects") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [{
            id: projectId,
            employer_user_id: employerId,
            title: "Build a Flask API",
            description: "A production backend",
            budget_min_minor: 80000,
            budget_max_minor: 120000,
            currency: "USD",
            status: "OPEN",
            skills: ["Python", "Flask"],
          }],
        }),
      });
    }
    if (url.pathname === `/api/backend/projects/${projectId}/recommendations`) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: runId,
          project_id: projectId,
          model_version: "rule-v1",
          feature_version: "matching-features-v1",
          candidate_set_version: "candidate-set-2026-08-23",
          items: [{
            freelancer_id: candidateId,
            rank: 1,
            score: 0.91,
            score_basis_points: 9100,
            features: { skill_match: 1, experience: 0.8, price_fit: 0.9, availability: 1, reputation: 0.95 },
            reasons: ["strong_skill_match", "available_now"],
          }],
        }),
      });
    }
    if (url.pathname === `/api/backend/projects/${projectId}/ai/price-estimate`) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          project_id: projectId,
          model_version: "pricing-baseline-v1",
          feature_version: "pricing-history-v1",
          currency: "USD",
          lower_minor: 80000,
          upper_minor: 115000,
          sample_count: 8,
          confidence: "LOW",
          method: "historical_proposal_iqr",
        }),
      });
    }
    if (url.pathname === `/api/backend/recommendations/${runId}/events`) {
      const payload = route.request().postDataJSON() as { event_type: string };
      eventTypes.push(payload.event_type);
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ id: "event-1", created: true }),
      });
    }
    return route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });

  await page.goto("/dashboard/ai");
  await expect(page.getByRole("heading", { level: 1, name: "Decision support, not hidden automation." })).toBeVisible();
  await page.getByRole("button", { name: "Analyze project" }).click();

  await expect(page.getByText("$800.00 – $1,150.00", { exact: true })).toBeVisible();
  await expect(page.getByText("91.0% match", { exact: true })).toBeVisible();
  await expect(page.getByText("Strong Skill Match", { exact: true })).toBeVisible();
  await expect(page.getByText("rule-v1", { exact: true })).toBeVisible();
  await expect(page.getByText("matching-features-v1", { exact: true })).toBeVisible();
  await expect.poll(() => eventTypes).toContain("IMPRESSION");
});

test("freelancer skill detection is visibly advisory and never presented as a profile mutation", async ({ page }) => {
  await routeSession(page, ["freelancer"], freelancerId);
  await page.route("**/api/backend/freelancers/me/ai/skill-suggestions", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        model_version: "skill-rules-v1",
        feature_version: "skill-text-features-v1",
        profile_mutated: false,
        suggestions: [{
          skill_id: "44444444-4444-4444-8444-444444444444",
          name: "Django",
          slug: "django",
          confidence: 0.96,
          evidence_source: "portfolio",
        }],
      }),
    }),
  );

  await page.goto("/dashboard/ai");
  await expect(page.getByRole("heading", { level: 2, name: "Skills we detected" })).toBeVisible();
  await expect(page.getByText("Suggestions are advisory only. Your profile is never changed without an explicit edit.")).toBeVisible();
  await expect(page.getByText("Django", { exact: true })).toBeVisible();
  await expect(page.getByText("96% confidence", { exact: true })).toBeVisible();
  await expect(page.getByText("profile mutated: no", { exact: true })).toBeVisible();
});
