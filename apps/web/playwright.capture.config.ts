import { defineConfig, devices } from "@playwright/test";

/**
 * Config for the docs-asset capture in `scripts/` — never the PR gate.
 *
 * The default config's `testDir: ./e2e` deliberately excludes this: the capture writes into
 * docs/screenshots, shells out to Pillow, and would fail CI on a box without python3. Same
 * preview server, so `just check` and `just capture-specimen` can share a warm build.
 */
export default defineConfig({
  testDir: "./scripts",
  fullyParallel: false,
  workers: 1,
  reporter: "list",
  use: { baseURL: "http://localhost:4173", trace: "off" },
  webServer: {
    command: "pnpm build && pnpm preview --port 4173 --strictPort",
    url: "http://localhost:4173",
    reuseExistingServer: true,
    timeout: 180_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
