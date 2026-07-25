import { expect, test } from "@playwright/test";
import { installApiFixtures } from "./fixtures/api";

/**
 * The chat page's populated state, in both directions (§8.6).
 *
 * `/chat`'s snapshot in rtl-ltr.spec.ts captures an empty thread, so nothing covered the thing
 * that page exists to do: stream a bilingual reply without tearing Arabic ligatures, then report
 * TTFT and tok/s. These tests drive a real send through the SSE reader and assert on the result.
 */
for (const lang of ["en", "ar"] as const) {
  test(`chat streams a bilingual reply in ${lang}`, async ({ page }) => {
    await page.addInitScript((l) => localStorage.setItem("sanad.lang", l), lang);
    await installApiFixtures(page);
    await page.goto("/chat");
    await expect(page.getByTestId("page-fallback")).toHaveCount(0);

    const box = page.getByRole("textbox").first();
    await box.fill("ما معدل الفائدة على حساب التوفير؟");
    await box.press("Enter");

    // the assistant's reply arrives in both scripts and finishes streaming
    const thread = page.getByRole("main");
    await expect(thread).toContainText("2.75%");
    await expect(thread).toContainText("subject to CBUAE rules");

    // Arabic must survive the grapheme-boundary buffer intact — a torn flush would leave the
    // word broken or reordered rather than exactly as the stream sent it (§8.6).
    await expect(thread).toContainText("يخضع حساب التوفير");

    await expect(page).toHaveScreenshot(`chat-streamed-${lang}.png`, {
      fullPage: false,
      mask: [page.locator("canvas")],
      timeout: 15_000,
    });
  });
}
