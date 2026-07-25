import { expect, test } from "@playwright/test";
import { CHAT_REPLY, installApiFixtures, installPacedChatStream } from "./fixtures/api";

/**
 * The chat page's populated state, and the invariant it exists to protect (§8.6).
 *
 * `/chat`'s snapshot in rtl-ltr.spec.ts captures an empty thread, so nothing covered a streamed
 * reply. These tests drive a real send through the SSE reader with a *paced* stream, so the reply
 * renders progressively and every intermediate state can be inspected.
 *
 * Arabic combining marks are what make this more than a string-assembly check: the fixture splits
 * a fathatan (U+064B) from its base letter across two deltas. Concatenating deltas yields the
 * correct final text whether or not GraphemeBuffer is in the path, so only the intermediate
 * renders can show a torn cluster.
 */

/**
 * The invariant, stated precisely: every state the user could have seen must be a prefix of the
 * final reply that ends **on a grapheme-cluster boundary**.
 *
 * "No state ends on a bare combining mark" sounds like the right check but is not: without
 * buffering the DOM shows the base letter first and acquires its fathatan on the next delta, so no
 * state ever ends on a lone mark — it ends *inside* the cluster. Cluster alignment is what
 * separates the two behaviours, and it catches reordered or dropped text for free.
 */
async function unalignedStates(page: import("@playwright/test").Page, reply: string) {
  return page.evaluate((full) => {
    const boundaries = new Set<number>([0]);
    let offset = 0;
    for (const { segment } of new Intl.Segmenter("ar", { granularity: "grapheme" }).segment(full)) {
      offset += segment.length;
      boundaries.add(offset);
    }
    const states = (window as unknown as { __streamStates: string[] }).__streamStates ?? [];
    return {
      count: states.length,
      bad: states
        .map((s) => s.replace(/\u258D$/, "")) // the streaming caret is not part of the reply
        .filter((s) => s.length > 0)
        .filter((s) => !full.startsWith(s) || !boundaries.has(s.length)),
    };
  }, reply);
}

for (const lang of ["en", "ar"] as const) {
  test(`chat streams a bilingual reply without tearing graphemes (${lang})`, async ({ page }) => {
    await page.addInitScript((l) => localStorage.setItem("sanad.lang", l), lang);
    await installApiFixtures(page);
    await installPacedChatStream(page);
    await page.goto("/chat");
    await expect(page.getByTestId("page-fallback")).toHaveCount(0);

    const box = page.getByRole("textbox").first();
    await box.fill("ما معدل الفائدة على حساب التوفير؟");
    await box.press("Enter");

    const thread = page.getByRole("main");
    await expect(thread).toContainText("subject to CBUAE rules");

    // the reply assembled exactly, in both scripts, with the split cluster made whole again
    await expect(thread).toContainText(CHAT_REPLY);
    expect(CHAT_REPLY).toContain("وفقاً");

    // …and every state it passed through was cluster-aligned. This is the assertion that fails
    // if GraphemeBuffer leaves the streaming path.
    const { count, bad } = await unalignedStates(page, CHAT_REPLY);
    expect(count).toBeGreaterThan(2); // the stream really did render progressively
    expect(bad, `states cutting a grapheme cluster: ${JSON.stringify(bad)}`).toEqual([]);

    await expect(page).toHaveScreenshot(`chat-streamed-${lang}.png`, {
      fullPage: false,
      mask: [page.locator("canvas")],
      timeout: 15_000,
    });
  });
}
