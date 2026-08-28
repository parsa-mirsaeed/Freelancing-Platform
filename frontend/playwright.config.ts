import { defineConfig } from "@playwright/test";

const fullMatrix = Boolean(process.env.PLAYWRIGHT_FULL_MATRIX);

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-first-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: fullMatrix
    ? [
        {
          name: "desktop-chromium",
          use: { browserName: "chromium", viewport: { width: 1440, height: 900 } },
        },
        {
          name: "desktop-firefox",
          use: { browserName: "firefox", viewport: { width: 1440, height: 900 } },
        },
        {
          name: "desktop-webkit",
          use: { browserName: "webkit", viewport: { width: 1440, height: 900 } },
        },
        {
          name: "mobile-chromium",
          use: {
            browserName: "chromium",
            viewport: { width: 390, height: 844 },
            isMobile: true,
            hasTouch: true,
          },
        },
        {
          name: "mobile-webkit",
          use: {
            browserName: "webkit",
            viewport: { width: 390, height: 844 },
            isMobile: true,
            hasTouch: true,
          },
        },
      ]
    : [
        {
          name: "desktop-chromium",
          use: { browserName: "chromium", viewport: { width: 1440, height: 900 } },
        },
        {
          name: "mobile-chromium",
          use: {
            browserName: "chromium",
            viewport: { width: 390, height: 844 },
            isMobile: true,
            hasTouch: true,
          },
        },
      ],
  webServer: [
    {
      command: "node tests/e2e/mock-backend.mjs",
      url: "http://127.0.0.1:8000/health/live",
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: "npm run dev -- --hostname 127.0.0.1",
      url: "http://127.0.0.1:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: { BACKEND_API_URL: process.env.BACKEND_API_URL ?? "http://127.0.0.1:8000" },
    },
  ],
});
