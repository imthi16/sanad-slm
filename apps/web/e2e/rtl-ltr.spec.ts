import { fileURLToPath } from "node:url";
import { type Page, expect, test } from "@playwright/test";

// Every page passes in BOTH directions (§8.6: Playwright captures RTL and LTR snapshots).
const ROUTES = ["/", "/chat", "/evals", "/tokenizer", "/edge", "/registry"] as const;

const FERTILITY_FIXTURE = fileURLToPath(new URL("./fixtures/fertility.json", import.meta.url));

/**
 * The Specimen's rule is measured from real token offsets, so an unserved
 * /v1/tokenize/fertility leaves the hero's signature element blank and the snapshots only ever
 * prove the empty state. Serving a fixture makes them cover the populated rule instead.
 *
 * The fixture is SYNTHETIC — plausible segmentations shaped to match each tokenizer's known
 * Arabic fertility ordering. It exists to pin layout, and no figure in it may be quoted
 * anywhere as a measurement (prime directive 5). Real numbers come from the live tokenizers.
 */
async function serveFertilityFixture(page: Page): Promise<void> {
  await page.route("**/v1/tokenize/fertility", (route) =>
    route.fulfill({ path: FERTILITY_FIXTURE, contentType: "application/json" }),
  );
}

for (const route of ROUTES) {
  for (const lang of ["en", "ar"] as const) {
    test(`${route} renders in ${lang} (${lang === "ar" ? "RTL" : "LTR"})`, async ({ page }) => {
      await page.addInitScript((l) => localStorage.setItem("sanad.lang", l), lang);
      await serveFertilityFixture(page);
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
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await page.getByRole("button", { name: /switch language|التبديل/i }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
});
