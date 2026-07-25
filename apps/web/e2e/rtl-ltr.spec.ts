import { expect, test } from "@playwright/test";
import { installApiFixtures } from "./fixtures/api";

// Every page passes in BOTH directions (§8.6: Playwright captures RTL and LTR snapshots).
const ROUTES = ["/", "/chat", "/evals", "/tokenizer", "/edge", "/registry"] as const;

/**
 * Every route renders against fixtures, so the baselines cover *populated* layouts. Without them
 * `/chat`, `/evals`, `/edge` and `/registry` only ever proved their empty states, and the
 * Specimen's rule — measured from real token offsets — was blank in all twelve images.
 *
 * The fixtures are synthetic and documented as such in ./fixtures/api.ts; none of their numbers
 * is a measurement.
 */
for (const route of ROUTES) {
  for (const lang of ["en", "ar"] as const) {
    test(`${route} renders in ${lang} (${lang === "ar" ? "RTL" : "LTR"})`, async ({ page }) => {
      await page.addInitScript((l) => localStorage.setItem("sanad.lang", l), lang);
      await installApiFixtures(page);
      await page.goto(route);

      // the <html dir lang> flip is the global bidi contract (§8.3)
      await expect(page.locator("html")).toHaveAttribute("lang", lang);
      await expect(page.locator("html")).toHaveAttribute("dir", lang === "ar" ? "rtl" : "ltr");

      // shell renders localized nav
      await expect(page.getByRole("navigation", { name: "primary" })).toBeVisible();

      // wait for the lazy page chunk to mount — nav lives in the Shell and renders while the
      // router Suspense fallback is still up; screenshotting then captures the skeleton
      await expect(page.getByTestId("page-fallback")).toHaveCount(0);

      // no horizontal overflow in either direction (classic RTL bug)
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);

      await expect(page).toHaveScreenshot(`${route.replaceAll("/", "_") || "home"}-${lang}.png`, {
        fullPage: false,
        mask: [page.locator("canvas")], // 3D content is non-deterministic
        // masked-WebGL captures are slow on software GL (ReadPixels stalls) with parallel
        // workers — the 5s default expires before two consecutive stable shots
        timeout: 15_000,
      });
    });
  }
}

test("language toggle flips direction live", async ({ page }) => {
  await installApiFixtures(page);
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await page.getByRole("button", { name: /switch language|التبديل/i }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
});
