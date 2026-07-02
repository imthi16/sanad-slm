import { expect, test } from "@playwright/test";

// Every page passes in BOTH directions (§8.6: Playwright captures RTL and LTR snapshots).
const ROUTES = ["/", "/chat", "/evals", "/tokenizer", "/edge", "/registry"] as const;

for (const route of ROUTES) {
  for (const lang of ["en", "ar"] as const) {
    test(`${route} renders in ${lang} (${lang === "ar" ? "RTL" : "LTR"})`, async ({ page }) => {
      await page.addInitScript((l) => localStorage.setItem("sanad.lang", l), lang);
      await page.goto(route);

      // the <html dir lang> flip is the global bidi contract (§8.3)
      await expect(page.locator("html")).toHaveAttribute("lang", lang);
      await expect(page.locator("html")).toHaveAttribute("dir", lang === "ar" ? "rtl" : "ltr");

      // shell renders localized nav
      await expect(page.getByRole("navigation", { name: "primary" })).toBeVisible();

      // no horizontal overflow in either direction (classic RTL bug)
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);

      await expect(page).toHaveScreenshot(`${route.replaceAll("/", "_") || "home"}-${lang}.png`, {
        fullPage: false,
        mask: [page.locator("canvas")], // 3D content is non-deterministic
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
