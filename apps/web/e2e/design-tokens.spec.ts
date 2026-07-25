import { expect, test } from "@playwright/test";

/**
 * Deterministic guards for the design system (CLAUDE.md §8.2, ADR-0005).
 *
 * Why these exist alongside the screenshots: the whole Night Dune → Rubrication palette change
 * landed *without* moving 10 of the 12 snapshot baselines past their diff threshold. Screenshot
 * comparison scores each pixel's colour delta against `threshold` (0.2 by default) before
 * counting it toward `maxDiffPixelRatio`, and one dark warm ground sits within that delta of
 * another dark cool ground. A palette swap is therefore close to invisible to pixel diffing on
 * text-sparse pages.
 *
 * Tightening the tolerance is the wrong lever: baselines are generated on a developer machine
 * and compared on an ubuntu runner, so most of that headroom is absorbing font-rasterisation
 * differences rather than real regressions. These assertions read computed style instead —
 * exact, machine-independent, and aimed at precisely what slipped through.
 */

/** The tokens whose values the product's identity actually rests on. */
const PALETTE = {
  canvas: "rgb(23, 19, 16)", //         --color-ink-950
  primaryText: "rgb(244, 236, 221)", // --color-sand-100 (and the Arabic script's own colour)
  instrument: "rgb(63, 191, 164)", //   --color-verdigris-400 — the one live/active/pass accent
  alarm: "rgb(228, 96, 63)", //         --color-cinnabar-400 — alarms only
  latinScript: "rgb(143, 167, 189)", // --color-pewter-400 — Latin marker in fertility visuals
} as const;

test.describe("design tokens", () => {
  test("palette tokens hold their values", async ({ page }) => {
    await page.goto("/");
    const resolved = await page.evaluate(() => {
      const probe = document.createElement("div");
      document.body.append(probe);
      const read = (value: string) => {
        probe.style.color = value;
        return getComputedStyle(probe).color;
      };
      const out = {
        canvas: read("var(--color-ink-950)"),
        primaryText: read("var(--color-sand-100)"),
        instrument: read("var(--color-verdigris-400)"),
        alarm: read("var(--color-cinnabar-400)"),
        latinScript: read("var(--color-pewter-400)"),
      };
      probe.remove();
      return out;
    });
    expect(resolved).toEqual(PALETTE);
  });

  test("the app paints on the ink canvas with paper-coloured text", async ({ page }) => {
    await page.goto("/");
    const body = await page.evaluate(() => {
      const s = getComputedStyle(document.body);
      return { background: s.backgroundColor, color: s.color };
    });
    expect(body.background).toBe(PALETTE.canvas);
    expect(body.color).toBe(PALETTE.primaryText);
  });

  // A fresh page per language: `addInitScript` re-runs on every navigation, so setting the
  // language twice on one page and reloading just restores the first value.
  test("Latin headings are set in Fraunces", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("sanad.lang", "en"));
    await page.goto("/");
    await expect(page.getByTestId("page-fallback")).toHaveCount(0);
    const family = await page
      .locator("h1")
      .first()
      .evaluate((el) => getComputedStyle(el).fontFamily);
    expect(family).toContain("Fraunces");
  });

  test("Arabic headings are set in Ruqaa, x-height matched", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("sanad.lang", "ar"));
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    await expect(page.getByTestId("page-fallback")).toHaveCount(0);
    const heading = await page
      .locator("h1")
      .first()
      .evaluate((el) => {
        const s = getComputedStyle(el);
        return { family: s.fontFamily, adjust: s.fontSizeAdjust };
      });
    expect(heading.family).toContain("Aref Ruqaa");
    // font-size-adjust is what keeps Ruqaa from setting smaller than its Latin counterpart
    expect(heading.adjust).not.toBe("none");
  });

  for (const lang of ["en", "ar"] as const) {
    test(`the wordmark keeps both display faces with the interface in ${lang}`, async ({
      page,
    }) => {
      await page.addInitScript((l) => localStorage.setItem("sanad.lang", l), lang);
      await page.goto("/");
      const faces = await page.locator("header a[href='/'] span[lang]").evaluateAll((els) =>
        els.map((el) => ({
          lang: el.getAttribute("lang"),
          family: getComputedStyle(el).fontFamily,
        })),
      );
      expect(faces).toHaveLength(2);
      // Regression guard: `:lang(ar) .font-display` (descendant combinator) used to drag the
      // lang="en" half onto the Arabic face, which carries no Latin glyphs — so "SANAD" rendered
      // in whatever generic serif the browser fell back to whenever the UI was Arabic.
      expect(faces.find((f) => f.lang === "ar")?.family).toContain("Aref Ruqaa");
      expect(faces.find((f) => f.lang === "en")?.family).toContain("Fraunces");
    });
  }

  /**
   * Read @font-face sources out of the CSSOM and watch what the browser actually fetches.
   *
   * `document.fonts` entries are FontFace objects, which expose no source URL — an earlier
   * version of this test mapped them to `f.src` and so compared an array of empty strings to an
   * empty array. It passed unconditionally. The CSSOM carries the real `src` descriptors, and the
   * request log catches anything injected after load.
   */
  async function externalFontSources(page: import("@playwright/test").Page) {
    return page.evaluate(() => {
      const found: string[] = [];
      for (const sheet of Array.from(document.styleSheets)) {
        let rules: CSSRuleList;
        try {
          rules = sheet.cssRules;
        } catch {
          // a cross-origin sheet cannot be read — that it exists at all is itself a finding
          if (sheet.href && /^https?:\/\//.test(sheet.href)) found.push(`stylesheet ${sheet.href}`);
          continue;
        }
        for (const rule of Array.from(rules)) {
          if (rule.constructor.name !== "CSSFontFaceRule") continue;
          const src = (rule as CSSFontFaceRule).style.getPropertyValue("src");
          for (const match of src.matchAll(/url\((['"]?)(https?:\/\/[^'")]+)\1\)/g)) {
            if (match[2]) found.push(match[2]);
          }
        }
      }
      return found;
    });
  }

  test("no external font is declared or fetched", async ({ page }) => {
    const fetched: string[] = [];
    page.on("request", (req) => {
      const url = req.url();
      if (req.resourceType() === "font" && !url.startsWith("http://localhost")) fetched.push(url);
    });

    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);

    expect(await externalFontSources(page)).toEqual([]);
    expect(fetched).toEqual([]);
  });

  test("the external-font check would actually catch one", async ({ page }) => {
    // Guards the guard: the previous implementation could not fail, so prove this one can.
    await page.goto("/");
    await page.evaluate(() => {
      const style = document.createElement("style");
      style.textContent =
        "@font-face { font-family: 'Smuggled'; src: url('https://fonts.example.com/x.woff2') format('woff2'); }";
      document.head.append(style);
    });
    expect(await externalFontSources(page)).toContain("https://fonts.example.com/x.woff2");
  });
});
