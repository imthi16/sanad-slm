/**
 * The Specimen (§8.4a, ADR-0005) — the hero, and the project's thesis made visible.
 *
 * A bilingual sentence is set once, intact, in the dual-script display pairing. Beneath it runs
 * a measured rule broken into one dash per token, so you can see exactly where the selected
 * tokenizer cut. Switching tokenizer re-cuts the rule under unchanged text: Arabic words fall
 * into four or five dashes while English words stay whole. That is Arabic tokenizer fertility,
 * shown rather than asserted.
 *
 * Why the marks sit *under* the text and never inside it: Arabic is a joining script, and text
 * shaping does not cross element boundaries. Wrapping each token in its own <span> would sever
 * the joins and render "التوفير" as four isolated letterforms — a typographic lie about the
 * input. The sentence therefore stays a single text node (which also lets per-glyph font
 * fallback set Arabic in Ruqaa and Latin in Fraunces), and token boundaries are measured with
 * the Range API instead.
 */
import type { TokenSegment } from "@/store/tokenizer";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

interface RuleDash {
  key: string;
  /** physical px offsets from the host box — Range rects are physical, so these must be too */
  left: number;
  top: number;
  width: number;
  script: TokenSegment["script"];
}

/** px shaved off each dash so consecutive tokens read as cut apart rather than continuous */
const CUT = 3;
/** clear air between the deepest descender and the rule */
const GAP = 5;
/** fallback share of the line box, used only if the browser withholds font metrics */
const RULE_AT = 0.95;

/**
 * How far below a line box's top the rule belongs.
 *
 * Range rects span the whole line box, whose bottom edge is a half-leading below the deepest
 * glyph — so no fixed fraction of it lands correctly for both Fraunces and Ruqaa at every fluid
 * size. Canvas gives the two numbers that actually decide this: where the baseline sits inside
 * the line box, and how far this specific string's ink descends past it (Ruqaa's ج and ي reach
 * much further than any Latin descender).
 */
function ruleOffset(para: HTMLElement, text: string, lineBox: number): number {
  try {
    const style = getComputedStyle(para);
    const ctx = document.createElement("canvas").getContext("2d");
    if (!ctx) return lineBox * RULE_AT;
    ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    ctx.textBaseline = "alphabetic";
    const m = ctx.measureText(text);
    if (!m.fontBoundingBoxAscent) return lineBox * RULE_AT;
    const halfLeading = (lineBox - (m.fontBoundingBoxAscent + m.fontBoundingBoxDescent)) / 2;
    const descent = Math.max(m.actualBoundingBoxDescent || 0, m.fontBoundingBoxDescent * 0.5);
    return Math.min(halfLeading + m.fontBoundingBoxAscent + descent + GAP, lineBox);
  } catch {
    return lineBox * RULE_AT;
  }
}

export function Specimen({
  text,
  segments,
  className,
}: {
  text: string;
  segments: TokenSegment[];
  className?: string;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLParagraphElement>(null);
  const [dashes, setDashes] = useState<RuleDash[]>([]);
  const [drawn, setDrawn] = useState(false);

  const measure = useCallback(() => {
    const host = hostRef.current;
    const para = textRef.current;
    const node = para?.firstChild;
    if (!host || !para || !node || node.nodeType !== Node.TEXT_NODE) {
      setDashes([]);
      return;
    }
    const base = host.getBoundingClientRect();
    const length = text.length;
    const range = document.createRange();
    const next: RuleDash[] = [];
    let offset: number | null = null;

    segments.forEach((segment, i) => {
      // Offsets come from the Rust tokenizer as codepoint indices; Range wants UTF-16 units.
      // They coincide for Arabic and Latin (both BMP), and clamping keeps a stale segment list
      // from throwing while a new measurement is in flight.
      const start = Math.min(segment.start, length);
      const end = Math.min(segment.end, length);
      if (end <= start) return;
      range.setStart(node, start);
      range.setEnd(node, end);
      // getClientRects is already bidi-reordered and returns one rect per visual run, so a
      // token straddling a script change splits into two dashes with no RTL special-casing.
      Array.from(range.getClientRects()).forEach((rect, j) => {
        if (rect.width < 0.5) return;
        // every line box in the paragraph is the same height, so this is measured once
        offset ??= ruleOffset(para, text, rect.height);
        next.push({
          key: `${i}-${j}`,
          left: rect.left - base.left,
          top: rect.top - base.top + offset,
          width: Math.max(rect.width - CUT, 1),
          script: segment.script,
        });
      });
    });
    setDashes(next);
  }, [segments, text]);

  useLayoutEffect(() => {
    measure();
  }, [measure]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const observer = new ResizeObserver(() => measure());
    observer.observe(host);
    // display faces load async; Ruqaa's metrics move the baseline when they arrive
    document.fonts?.ready.then(measure);
    return () => observer.disconnect();
  }, [measure]);

  // the rule draws itself in once, on the first measurement that produced dashes
  useEffect(() => {
    if (!dashes.length || drawn) return;
    const frame = requestAnimationFrame(() => setDrawn(true));
    return () => cancelAnimationFrame(frame);
  }, [dashes.length, drawn]);

  return (
    <div ref={hostRef} className={`relative ${className ?? ""}`}>
      <p ref={textRef} dir="auto" className="specimen">
        {text}
      </p>
      {/* The rule restates what the ledger below already says in words, so it is decorative
          to assistive tech. */}
      <div aria-hidden="true">
        {dashes.map((dash, i) => (
          <span
            key={dash.key}
            className="specimen-dash"
            data-script={dash.script}
            style={{
              left: `${dash.left}px`,
              top: `${dash.top}px`,
              width: drawn ? `${dash.width}px` : 0,
              transitionDelay: drawn && i < 40 ? `${i * 10}ms` : "0ms",
            }}
          />
        ))}
      </div>
    </div>
  );
}
