# CLAUDE.md — `apps/web/` · React 19 + R3F dashboard

> Loads when Claude works under `apps/web/`. The root [`CLAUDE.md`](../../CLAUDE.md) holds the prime
> directives — including **prime directive 3, Arabic is a first-class citizen** — read it first; it
> wins on conflict.

## 8.1 Design brief (deliberate, not default) — see ADR-0005

Subject: a sovereign bilingual model platform for Gulf banking. Audience: UAE ML hiring managers
and researchers who will judge craft in 90 seconds. The page's job: prove Arabic-first
engineering depth instantly. **The signature element is the Specimen (§8.4a):** the bilingual
sentence set intact at display size, with a measured rule beneath it broken into one dash per
token, re-cutting live as you switch tokenizer — the project's core insight as evidence you can
read, not an effect you watch. Everything else stays quiet and disciplined so that one moment
carries the identity. Explicitly avoid the stock AI looks (cream+serif+terracotta;
near-black+acid-green; broadsheet hairlines) — this design's identity comes from **dual-script
typography treated as material** and a **lamplit-manuscript ground with rubricator's pigments
as instrumentation**.

## 8.2 Design tokens

The palette and type stack live in `src/styles/tokens.css` as a Tailwind v4 `@theme` block — read
that file for the values. The naming scheme: `--color-ink-*` (warm ink canvas → hairline rules),
`--color-sand-*` (rag-paper text, and the Arabic script's colour), `--color-pewter-400` (Latin
script marker, fertility visuals only), `--color-verdigris-400` (the one instrument accent),
`--color-cinnabar-400` (alarms only).

Rules — these are the non-derivable half, and they are what the design-token e2e assertions check:
fluid type via `clamp()` (Latin display 2.1–4.25rem, Arabic 1.9–3.6rem — Ruqaa needs more
leading and no negative tracking); `:lang(ar)` swaps to `--font-ar` and bumps line-height to 1.8;
**`font-size-adjust: 0.5` on the Arabic display face** — Ruqaa draws small for its em, and matching
x-heights rather than font-sizes is what makes the two scripts land as equals (prime directive 3);
`opsz` is left unset on Fraunces so `font-optical-sizing: auto` tracks it to the rendered size;
verdigris appears only on live numbers, active nav and the cheapest row — never as large fills;
sections are separated by hairline `.rule-top` bands rather than bordered cards; `.eyebrow` is the
one repeated label form (spaced mono small caps in Latin, weight-differentiated in Arabic, where
uppercase and letter-spacing are meaningless); unmeasured figures render `—` via `.unmeasured`,
never a plausible-looking number; motion durations 150/300/600 ms with a single easing
(`cubic-bezier(.2,.8,.2,1)`); `prefers-reduced-motion` collapses all of it.

Fonts are self-hosted @fontsource, script-subsetted (ADR-0005): Fraunces var (Latin display, WONK 1
SOFT 0), Aref Ruqaa (AR display, 700), IBM Plex Sans + Plex Sans Arabic (body/UI, one superfamily),
Plex Mono (data/labels). **No Google Fonts CDN in sovereign mode — ever** (`just verify-no-cdn`).

## 8.3 Routes & features

`/` Home (hero + headline results strip) · `/chat` bilingual streaming chat · `/evals` benchmark
+ judge dashboard · `/tokenizer` Fertility Lab (corpus-level detail behind the hero's sentence) · `/edge` live
edge-node telemetry · `/registry` artifact lineage. Global: language toggle (EN/AR) that flips
`<html dir lang>`, sovereign-mode badge (reads `/v1/models` meta), model picker.

## 8.4 3D scenes (`src/three/`) — the centerpiece

Shared: one `<Canvas>` per scene, `dpr={[1, 2]}`, `frameloop="demand"` except during active
animation, `<AdaptiveDpr>` + `PerformanceMonitor` from drei degrade quality before dropping
frames; postprocessing limited to subtle `Bloom` (luminanceThreshold ≈ 0.85) + `Vignette`;
every scene has a static `poster.webp` fallback (no WebGL / reduced-motion / mobile-low).

**(a) The Specimen — hero + working demo (signature; DOM, not WebGL — ADR-0005).**
`components/fertility/Specimen.tsx`. A real sentence (user-editable; defaults to a bilingual
banking sentence) is set **once, intact**, at display size, in the dual-script pairing — one text
node, so per-glyph font fallback puts Arabic in Ruqaa and Latin in Fraunces. Beneath it runs a
measured rule broken into one dash per token, coloured by script (paper for Arabic, pewter for
Latin); the gap between dashes is the cut. On tokenizer switch the rule re-cuts under unchanged
text and the dashes morph into place: Arabic words fall into four or five, English words stay
whole. That is the visual argument, and it is evidence rather than ambience.

**Never mark tokens by splitting the text into per-token elements.** Text shaping does not cross
element boundaries, so `<span>`-per-token severs Arabic's joins and renders `التوفير` as isolated
letterforms — a typographic lie about the input. Boundaries are measured with
`Range.getClientRects()` instead, which the browser returns already bidi-reordered (one rect per
visual run), so mixed-script RTL needs no special-casing. The rule's vertical placement is derived
from canvas font metrics — baseline position inside the line box plus the string's own ink descent
— not a tuned fraction, so it holds across the fluid scale and Ruqaa's deep descenders.

Beneath it, `TokenizerLedger.tsx` prices **all five tokenizers at once** (tokens · tokens/word ·
×cost, cheapest marked); selection only chooses which row the rule illustrates. The comparison is
a column you read, not a sequence you have to remember.

**FertilityField (3D) is the opt-in second reading**, collapsed by default: the same
`POST /v1/tokenize/fertility` segments drive glyph-particles (instanced quads sampling an MSDF
atlas built at startup — `lib/glyphAtlas.ts`; Arabic shaped in DOM first, then rasterized, so
ligatures stay correct) regrouping into token clusters via `useTokenClusters.ts`, cream for
Arabic and pewter for Latin. Interaction: drag to orbit (damped), scroll passes through.
Budget: ≤ 1,200 instanced glyphs, one draw call per script, custom shader (position lerp +
cluster color) — no per-glyph meshes.

**(b) PipelineOrbit — architecture as space (`/` section 2).**
Five glass panels (Data → QLoRA → Quantize → Eval → Edge) orbit a slowly-rotating core; drei
`ScrollControls` scrubs the camera along the arc; clicking a panel routes to its page. Panels
are `MeshTransmissionMaterial`-lite (or plain translucent standard material if GPU budget
complains); labels via drei `<Text>` (troika) in both scripts.

**(c) EdgeBoard — live telemetry (`/edge`).**
A low-poly edge board (single glTF ≤ 300 KB, draco-compressed, authored once) with emissive
heat responding to live watts from `/v1/telemetry/stream`; verdigris needle gauges (tok/s, °C, W)
are HTML overlays (drei `<Html>`) so numbers stay crisp and accessible. SSE hook `lib/sse.ts`
reconnects with backoff.

## 8.5 State & data

TanStack Query for all REST (staleTime tuned per resource; eval runs 60 s); zustand for
UI/tokenizer/3D-shared state only; generated client from OpenAPI (`just api-types` →
`src/lib/api/`); never hand-write fetch types.

## 8.6 Bilingual & bidi correctness (test-covered, non-negotiable)

- `dir` flips at `<html>`; components use **logical properties only** (`ms-*`, `pe-*`,
  `text-start`) — a Biome-assisted grep in CI fails on `ml-|mr-|pl-|pr-|text-left|text-right`.
- Chat messages get `dir="auto"` per message; mixed-script inline spans wrapped with
  `unicode-bidi: isolate`.
- **Streaming Arabic must not tear ligatures:** buffer SSE deltas and flush on grapheme
  boundaries via `Intl.Segmenter('ar', {granularity: 'grapheme'})` (`lib/bidi.ts`).
- Numerals: `Intl.NumberFormat(locale)`; a settings toggle for Eastern Arabic numerals
  (`ar-u-nu-arab` — the UAE/MSA Arabic-Indic digits ٠١٢٣; CLDR `arabext` is the
  Persian/Urdu set and is wrong here) in AR mode.
- Playwright captures RTL **and** LTR snapshots for every page, **served from
  `e2e/fixtures/api.ts`** so the baselines cover populated layouts rather than empty states.
- **Palette and typeface regressions get deterministic assertions, not pixel diffing**
  (`e2e/design-tokens.spec.ts`). Screenshot comparison scores each pixel against `threshold`
  before counting it toward `maxDiffPixelRatio`, so one dark ground sits within tolerance of
  another: the entire ADR-0005 palette change moved only 2 of 12 baselines. Tolerance is not the
  lever to tighten — baselines are authored on a dev machine and compared on an ubuntu runner, so
  the headroom absorbs font rasterisation. Assert computed style instead.
- **Language-scoped CSS uses `:lang()` on the element, never as a descendant combinator.**
  `:lang(ar) .font-display` also captures `lang="en"` children inside an Arabic page — that is
  what made the wordmark's Latin half fall back to a generic serif. `:lang()` already matches on
  inherited language, so the descendant form buys nothing and breaks mixed-script markup.

## 8.7 Frontend quality bars

Lighthouse (desktop): ≥ 90 on non-3D routes, ≥ 75 on `/` with hero; JS ≤ 350 KB gzip initial,
three.js chunk lazy-loaded per scene (`import()` + Suspense skeleton); a11y: visible focus,
`aria-live="polite"` on streaming message + token HUD, canvas has text alternative + skip link;
fonts subsetted (Latin + Arabic ranges) and self-hosted — `just verify-no-cdn` gate.

Inner-loop commands are in root [`CLAUDE.md`](../../CLAUDE.md) §12.1.
