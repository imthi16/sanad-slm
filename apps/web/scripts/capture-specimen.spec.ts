import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { installApiFixtures } from "../e2e/fixtures/api";

/**
 * Re-record the README's hero GIF (`just capture-specimen`).
 *
 * Lives in `scripts/` and not in `e2e/`, deliberately: it writes files, shells out to Pillow and
 * takes ~20 s, none of which belongs in the PR gate. `playwright.config.ts` only picks up `e2e/`,
 * so the suite never runs this; `playwright.capture.config.ts` points here.
 *
 * **The tokenizer data is measured, not fixture.** `installApiFixtures` populates the rest of the
 * page (models, eval runs, telemetry), and then `/v1/tokenize/fertility` is overridden with the
 * payload `apps/api/scripts/measure_specimen.py` produced by calling the API's own fertility
 * service over the synced tokenizer.json files. Playwright matches routes newest-first, so the
 * later handler wins. What the recording shows — token counts, and every dash boundary — is what
 * those tokenizers actually do to this sentence. The two gated tokenizers are absent from the
 * payload and the ledger prints `—` for them, which is the product behaving correctly (§8.2)
 * rather than a gap to paper over.
 */

const PAYLOAD = fileURLToPath(
  new URL("../../../docs/screenshots/specimen-demo-payload.json", import.meta.url),
);
const OUT_GIF = fileURLToPath(
  new URL("../../../docs/screenshots/specimen-demo.gif", import.meta.url),
);
const ASSEMBLER = fileURLToPath(new URL("./assemble_gif.py", import.meta.url));
const FRAME_DIR = fileURLToPath(new URL("../.capture-frames/", import.meta.url));

/**
 * The crop is measured from the page, not hardcoded: the previous recording's fixed clip silently
 * stopped framing the hero when the copy above it changed length, and a GIF that has drifted
 * off its subject is not obvious until someone opens the README.
 */
const VIEWPORT = { width: 1180, height: 1000 };

/** Rows to walk. Cheapest first is not the story — start where the reader starts (qwen3). */
const ROWS = ["qwen3", "allam", "falcon-h1"] as const;
/** Frames sampled across each row's morph, and how long the settled state holds. */
const MORPH_FRAMES = 3;
const MORPH_STEP_MS = 130;
const HOLD_MS = 1700;

test("capture the Specimen demo", async ({ page }) => {
  rmSync(FRAME_DIR, { recursive: true, force: true });
  mkdirSync(FRAME_DIR, { recursive: true });

  await page.setViewportSize(VIEWPORT);
  await installApiFixtures(page);
  // measured tokenizer output overrides the synthetic fertility fixture (see the note above)
  await page.route("**/v1/tokenize/fertility", (route) =>
    route.fulfill({ path: PAYLOAD, contentType: "application/json" }),
  );

  await page.goto("/");
  // the rule only exists once the measurement lands and the dashes have been laid out
  await expect(page.locator(".specimen-dash").first()).toBeVisible();
  await page.waitForFunction(() => document.fonts.status === "loaded");

  // the subject is exactly two bands: the specimen with its rule, and the ledger pricing it
  const clip = await page.evaluate(() => {
    const section = (el: Element | null) => el?.closest("section") ?? null;
    const specimen = section(document.querySelector(".specimen"));
    const ledger = section(document.querySelector("fieldset"));
    if (!specimen || !ledger) throw new Error("hero sections not found — has Home.tsx moved?");
    const a = specimen.getBoundingClientRect();
    const b = ledger.getBoundingClientRect();
    const top = Math.min(a.top, b.top) + window.scrollY;
    const bottom = Math.max(a.bottom, b.bottom) + window.scrollY;
    return {
      x: Math.floor(Math.min(a.left, b.left)),
      y: Math.floor(top),
      width: Math.ceil(Math.max(a.right, b.right) - Math.min(a.left, b.left)),
      height: Math.ceil(bottom - top),
    };
  });
  expect(clip.height).toBeGreaterThan(300); // a collapsed crop means the page never painted

  const frames: { file: string; duration: number }[] = [];
  let index = 0;
  const shoot = async (duration: number) => {
    const file = `${FRAME_DIR}/f${String(index++).padStart(3, "0")}.png`;
    await page.screenshot({ path: file, clip, fullPage: true });
    frames.push({ file, duration });
  };

  await shoot(HOLD_MS + 1000); // opening hold: give a reader time to see the sentence intact

  for (const row of ROWS.slice(1)) {
    await page.getByRole("button", { name: new RegExp(`^${row}`) }).click();
    for (let i = 0; i < MORPH_FRAMES; i++) {
      await shoot(MORPH_STEP_MS);
      await page.waitForTimeout(MORPH_STEP_MS);
    }
    await shoot(HOLD_MS); // settled: long enough to read the row's tokens/word
  }

  // return to qwen3 so the loop closes where it began — the Arabic tax re-appears rather than
  // the GIF snapping back to it mid-read
  await page.getByRole("button", { name: /^qwen3/ }).click();
  for (let i = 0; i < MORPH_FRAMES; i++) {
    await shoot(MORPH_STEP_MS);
    await page.waitForTimeout(MORPH_STEP_MS);
  }

  writeFileSync(`${FRAME_DIR}/frames.json`, JSON.stringify(frames, null, 2));
  // Pillow assembles the GIF: node has no GIF encoder in this dependency tree, and adding one
  // for a docs asset does not earn its place in the lockfile (§14.3).
  const assembled = execFileSync("python3", [ASSEMBLER, `${FRAME_DIR}/frames.json`, OUT_GIF], {
    encoding: "utf-8",
  });
  console.log(assembled.trim());
  rmSync(FRAME_DIR, { recursive: true, force: true });
});

/**
 * The two homepage stills the README leads with, from the same measured payload.
 *
 * They used to come from the synthetic fixture, which put one set of token counts at the top of
 * the README and a different set in the GIF a few lines down — for the same sentence. Recapturing
 * them here keeps every published Specimen image showing the same real measurement.
 */
for (const lang of ["en", "ar"] as const) {
  test(`capture the homepage still (${lang})`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.addInitScript((l) => localStorage.setItem("sanad.lang", l), lang);
    await installApiFixtures(page);
    await page.route("**/v1/tokenize/fertility", (route) =>
      route.fulfill({ path: PAYLOAD, contentType: "application/json" }),
    );

    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("dir", lang === "ar" ? "rtl" : "ltr");
    await expect(page.locator(".specimen-dash").first()).toBeVisible();
    await page.waitForFunction(() => document.fonts.status === "loaded");

    await page.screenshot({
      path: fileURLToPath(new URL(`../../../docs/screenshots/home-${lang}.png`, import.meta.url)),
    });
  });
}
