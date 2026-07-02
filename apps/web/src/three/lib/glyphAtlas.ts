/**
 * Glyph atlas for FertilityField (§8.4a).
 *
 * Arabic shaping cannot be done glyph-by-glyph (isolated forms ≠ joined forms), so shaping
 * happens in the DOM first: the sentence is split into *units* — Arabic words (kept whole so
 * ligatures/joining stay correct) and Latin graphemes — and each unit is rasterized once into
 * a canvas atlas. Instanced quads sample the atlas: one draw call per script (budget: ≤1200
 * instances). An MSDF pipeline can replace the raster atlas later without touching consumers.
 */
import * as THREE from "three";

export interface AtlasEntry {
  /** uv rect in the atlas texture */
  u0: number;
  v0: number;
  u1: number;
  v1: number;
  /** unit size in world units (aspect-preserving) */
  width: number;
  height: number;
  text: string;
  script: "ar" | "en";
  /** character offset of this unit in the source sentence */
  start: number;
  end: number;
}

export interface GlyphAtlas {
  texture: THREE.CanvasTexture;
  entries: AtlasEntry[];
}

const AR_RE = /[؀-ۿݐ-ݿ]/;
const CELL_PAD = 6;
const FONT_PX = 56;
const MAX_INSTANCES = 1200; // §8.4a budget

interface Unit {
  text: string;
  script: "ar" | "en";
  start: number;
  end: number;
}

/** Split into Arabic words (whole, shaping-safe) + Latin/digit graphemes + skip spaces. */
export function splitUnits(sentence: string): Unit[] {
  const units: Unit[] = [];
  const wordRe = /\S+/g;
  const seg = new Intl.Segmenter(undefined, { granularity: "grapheme" });
  for (const match of sentence.matchAll(wordRe)) {
    const word = match[0];
    const base = match.index ?? 0;
    if (AR_RE.test(word)) {
      units.push({ text: word, script: "ar", start: base, end: base + word.length });
    } else {
      let offset = 0;
      for (const g of seg.segment(word)) {
        units.push({
          text: g.segment,
          script: "en",
          start: base + offset,
          end: base + offset + g.segment.length,
        });
        offset += g.segment.length;
      }
    }
    if (units.length >= MAX_INSTANCES) break;
  }
  return units.slice(0, MAX_INSTANCES);
}

function fontFor(script: "ar" | "en"): string {
  return script === "ar"
    ? `${FONT_PX}px "IBM Plex Sans Arabic", sans-serif`
    : `${FONT_PX}px "Space Grotesk", sans-serif`;
}

/** Rasterize all units of one script into a single atlas texture. */
export function buildAtlas(sentence: string, script: "ar" | "en"): GlyphAtlas | null {
  const units = splitUnits(sentence).filter((u) => u.script === script);
  if (units.length === 0) return null;

  const measure = document.createElement("canvas").getContext("2d");
  if (!measure) return null;
  measure.font = fontFor(script);

  const sizes = units.map((u) => {
    const m = measure.measureText(u.text);
    return {
      w: Math.ceil(m.width) + CELL_PAD * 2,
      h: Math.ceil(FONT_PX * 1.5) + CELL_PAD * 2,
    };
  });

  // shelf packing into a power-of-two square-ish atlas
  const atlasWidth = 1024;
  let x = 0;
  let y = 0;
  let rowH = 0;
  const positions = sizes.map((s) => {
    if (x + s.w > atlasWidth) {
      x = 0;
      y += rowH;
      rowH = 0;
    }
    const pos = { x, y };
    x += s.w;
    rowH = Math.max(rowH, s.h);
    return pos;
  });
  const atlasHeight = THREE.MathUtils.ceilPowerOfTwo(y + rowH);

  const canvas = document.createElement("canvas");
  canvas.width = atlasWidth;
  canvas.height = atlasHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.font = fontFor(script);
  ctx.textBaseline = "top";
  ctx.fillStyle = "#ffffff"; // tinted per-instance in the shader
  // DOM shaping guarantee: fillText of a whole Arabic word shapes via the platform text
  // engine (harfbuzz), so ligatures/joining forms are correct in the raster.
  units.forEach((u, i) => {
    const p = positions[i];
    if (!p) return;
    ctx.fillText(u.text, p.x + CELL_PAD, p.y + CELL_PAD);
  });

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.generateMipmaps = true;
  texture.minFilter = THREE.LinearMipmapLinearFilter;

  const entries: AtlasEntry[] = units.map((u, i) => {
    const p = positions[i];
    const s = sizes[i];
    if (!p || !s) throw new Error("atlas packing mismatch");
    return {
      u0: p.x / atlasWidth,
      v0: 1 - (p.y + s.h) / atlasHeight,
      u1: (p.x + s.w) / atlasWidth,
      v1: 1 - p.y / atlasHeight,
      width: (s.w / FONT_PX) * 0.5,
      height: (s.h / FONT_PX) * 0.5,
      text: u.text,
      script,
      start: u.start,
      end: u.end,
    };
  });

  return { texture, entries };
}
