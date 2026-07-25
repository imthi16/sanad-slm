# ADR-0005: The Specimen hero; "Rubrication" palette and dual-script display pairing

Date: 2026-07-25 · Status: accepted · Amends: CLAUDE.md §8.1, §8.2, §8.4(a)

## Context

P0 shipped §8's design brief literally: the Night Dune tokens, the four named typefaces, and a
FertilityField WebGL hero. Reviewing the built result against what the brief actually asked for
("the signature element is live tokenization… dual-script typography treated as material"), three
gaps stood out.

1. **The signature element did not carry the argument.** The 3D hero rendered the sentence as a
   drifting cloud of glyph particles. Particle clouds do not let you compare anything: you could
   not see which words got cut, or where. The project's central insight — that an English-first
   tokenizer shatters Arabic words — arrived as ambient motion rather than evidence.
2. **The typography was not doing the work the brief assigned it.** The hero headline was a
   left-aligned grotesk sentence in Space Grotesk (the default display face of the era), with
   Arabic reduced to a `:lang(ar)` font swap. Nothing in the layout treated the two scripts as
   material.
3. **The palette read as a generic dark dashboard.** Blue-slate canvas plus gold accent plus
   cream text is the near-black-and-one-accent look that appears regardless of subject. Nothing
   in it came from this project's world.

A fourth problem was latent: the comparison was **sequential**. Five tokenizer pills and one HUD
meant the reader had to click through and hold four numbers in memory to notice the tax.

## Decisions

1. **The Specimen replaces the 3D scene as the hero** (`components/fertility/Specimen.tsx`).
   The bilingual sentence is set once, intact, at display size in the dual-script pairing, and a
   measured rule runs beneath it broken into one dash per token. Switching tokenizer re-cuts the
   rule under unchanged text. Arabic words drop into four or five dashes; English words stay
   whole. Same data as before, from the same `POST /v1/tokenize/fertility` segments — but as
   evidence you can read rather than an effect you watch.

   The marks sit *under* the text and never inside it, because text shaping does not cross
   element boundaries: wrapping each token in its own `<span>` severs Arabic's joins and renders
   `التوفير` as isolated letterforms, which would be a typographic lie about the input. The
   sentence stays one text node and token boundaries are measured with `Range.getClientRects()`,
   which is bidi-reordered by the browser and so needs no RTL special-casing. Rule placement is
   derived from canvas font metrics (baseline position within the line box plus the string's own
   ink descent) rather than a tuned fraction, so it survives the fluid type scale and Ruqaa's
   deep descenders.

   Consequences: the hero needs no GPU, the text stays selectable and screen-readable, it renders
   crisply in the RTL/LTR snapshots, and it costs no three.js payload.

2. **FertilityField is demoted to an opt-in "field view"**, collapsed by default on `/`. It keeps
   the scene (and §8.4a's instancing/atlas work) as a second reading of the same measurement
   instead of deleting it, and it no longer owns the first impression. Its cluster colours were
   re-coded to match the Specimen.

3. **All five tokenizers are priced at once** (`TokenizerLedger.tsx`): a ruled table of tokens,
   tokens/word and ×cost, cheapest marked, selection only choosing which row the rule
   illustrates. The comparison becomes a column you read instead of a sequence you remember.

4. **Palette: "Rubrication"** replaces Night Dune. A warm ink canvas (`ink-950 #171310`) with
   rag-paper text, and instrument colours taken from the two pigments a rubricator kept on the
   desk: copper green (`verdigris-400`, the single live/active/pass accent) and red lead
   (`cinnabar-400`, alarms only). Token renames: `dune-*` → `ink-*`, `brass-400` + `teal-400` →
   `verdigris-400` (both meant "live/positive", so they collapse), `claret-500` →
   `cinnabar-400`. Badge tones collapse to `live | sand | alarm`.

   **Arabic takes the primary paper colour and Latin the quieter cool one** (`pewter-400`).
   Previously Arabic was marked teal against sand-coloured default text, which cast the Arabic
   run as the special case in an Arabic-first product. Inverting it is the palette stating
   prime directive 3.

5. **Type: two calligraphic display faces, one neutral superfamily beneath.**
   - Latin display: **Fraunces Variable** (all four axes, latin subset, 120 KB) replacing Space
     Grotesk. `WONK 1, SOFT 0` for the splayed sharp terminals; `opsz` deliberately left unset so
     `font-optical-sizing: auto` tracks it to the rendered size.
   - Arabic display: **Aref Ruqaa 700** replacing Amiri — a Ruqaa hand whose stroke contrast
     answers Fraunces' from an unrelated tradition, where Amiri's Naskh sat awkwardly beside a
     geometric grotesk.
   - Body/UI: **IBM Plex Sans** + **IBM Plex Sans Arabic** — one superfamily across both scripts,
     replacing Inter (which shared nothing with the Arabic face).
   - Data/labels: **IBM Plex Mono**, new. Tokens, hashes, counts and the eyebrow label form.

   Ruqaa draws small for its em, so Arabic set at the same `font-size` as its Latin neighbour
   reads as the smaller of the two. `font-size-adjust: 0.5` on the Arabic display face and on the
   Specimen matches x-heights instead of font-sizes, so the scripts land as equals.

6. **Cards give way to ruled bands.** `--radius-panel` drops to 0.25rem and page sections are
   separated by hairlines (`.rule-top`) rather than bordered panels. The Specimen sits directly
   on the page ground: it is the artefact under examination, not one panel among several.

7. **The results strip becomes a ledger with a "traces to" column** — metric, value, and where
   the figure comes from. Unmeasured figures stay em-dashes reading "not yet measured · P4".
   Prime directive 5 becomes a visible column rather than a promise in this file.

8. **The RTL/LTR snapshots now cover a populated hero.** `e2e/fixtures/fertility.json` is served
   via `page.route` for every snapshot test, because the Specimen's rule is measured from real
   token offsets and an unserved endpoint left the signature element blank in all 12 baselines.
   The fixture is **synthetic** — plausible segmentations shaped to match each tokenizer's known
   Arabic fertility ordering — and exists to pin layout. No figure in it may be quoted anywhere
   as a measurement.

## Consequences

- CLAUDE.md §8.1, §8.2 and §8.4(a) are rewritten to match; §15 is unaffected.
- Four `@fontsource` packages added (`fraunces`, `aref-ruqaa`, `ibm-plex-sans`, `ibm-plex-mono`),
  three removed (`space-grotesk`, `inter`, `amiri`). All self-hosted and script-subsetted;
  `just verify-no-cdn` still passes. `PipelineOrbit`'s troika font URL repoints to Plex Sans.
- All 12 snapshot baselines were regenerated. Note for future work: the default per-pixel
  threshold absorbed the entire dark-to-dark palette change on the text-sparse routes — only
  `/` and `/edge` exceeded `maxDiffPixelRatio: 0.02` on their own. The baselines were force-
  regenerated so none carry stale colour, but the tolerance is looser than §8.6's "bidi
  regressions are the #1 bug class" posture implies and is worth tightening.
- Arabic strings for the new copy are machine-drafted and carry `"_review": "pending-native"`.
- Not addressed here: `/chat`, `/evals`, `/tokenizer`, `/edge` and `/registry` received the token
  rename only, not a layout pass. They are coherent in the new palette but still card-based.
