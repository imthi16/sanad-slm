/**
 * Bidi-safe streaming (§8.6, non-negotiable): SSE deltas are buffered and flushed on grapheme
 * boundaries via Intl.Segmenter so Arabic ligatures/diacritics never tear mid-render.
 */

const segmenter = new Intl.Segmenter("ar", { granularity: "grapheme" });

// Arabic combining marks & joiners that must never start a flushed chunk alone.
const TRAILING_COMBINER = /[ً-ٰٟۖ-ۭ‍]$/;

export class GraphemeBuffer {
  private pending = "";

  /**
   * Feed a raw streamed delta; returns the text that is safe to append to the DOM now.
   * The final grapheme is held back while it could still receive combining marks from the
   * next delta; call flush() at stream end to drain it.
   */
  push(delta: string): string {
    this.pending += delta;
    const graphemes = [...segmenter.segment(this.pending)].map((s) => s.segment);
    if (graphemes.length <= 1) return "";
    // hold back the last grapheme — it may still grow (lam-alef, shadda+haraka, ZWJ chains)
    const safe = graphemes.slice(0, -1).join("");
    const last = graphemes[graphemes.length - 1] ?? "";
    if (TRAILING_COMBINER.test(safe)) {
      // combiner at the boundary: keep one more grapheme back
      const safer = graphemes.slice(0, -2).join("");
      this.pending = (graphemes[graphemes.length - 2] ?? "") + last;
      return safer;
    }
    this.pending = last;
    return safe;
  }

  flush(): string {
    const rest = this.pending;
    this.pending = "";
    return rest;
  }
}

/** Per-message direction for chat bubbles: dir="auto" semantics, resolved explicitly. */
export function textDirection(text: string): "rtl" | "ltr" {
  const first = text.match(/[؀-ۿݐ-ݿ]|[A-Za-z]/);
  if (!first) return "ltr";
  return /[؀-ۿݐ-ݿ]/.test(first[0]) ? "rtl" : "ltr";
}

/** Wrap mixed-script inline fragments so surrounding bidi context can't reorder them. */
export function isolate(text: string): string {
  return `⁦${text}⁩`; // LRI…PDI would force LTR; FSI auto-detects:
}

export function isolateAuto(text: string): string {
  return `⁨${text}⁩`; // FSI … PDI
}
