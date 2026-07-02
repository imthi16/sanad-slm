import { defineConfig, devices } from "@playwright/test";

// RTL + LTR snapshots for every page — bidi regressions are the #1 bug class here (§3.4, §8.6).
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:4173",
    trace: "on-first-retry",
  },
  webServer: {
    command: "pnpm build && pnpm preview --port 4173 --strictPort",
    url: "http://localhost:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  expect: {
    toHaveScreenshot: { maxDiffPixelRatio: 0.02 },
  },
});
