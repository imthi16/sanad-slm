import { GraphemeBuffer, textDirection } from "@/lib/bidi";
import { describe, expect, it } from "vitest";

describe("GraphemeBuffer — streaming Arabic must not tear ligatures (§8.6)", () => {
  it("holds back the trailing grapheme while it can still grow", () => {
    const buf = new GraphemeBuffer();
    // "كَ" arrives split across deltas: base letter then its haraka
    const first = buf.push("مرحبا كَ");
    expect(first.endsWith("كَ")).toBe(false); // the possibly-growing tail is withheld
    const rest = buf.push("تَبَ");
    const final = rest + buf.flush();
    expect((first + final).normalize("NFC")).toBe("مرحبا كَتَبَ".normalize("NFC"));
  });

  it("never emits a bare combining mark at a flush boundary", () => {
    const buf = new GraphemeBuffer();
    const chunks = ["السَّ", "لَامُ عَلَيْ", "كُمْ"];
    let out = "";
    for (const c of chunks) out += buf.push(c);
    out += buf.flush();
    expect(out.normalize("NFC")).toBe("السَّلَامُ عَلَيْكُمْ".normalize("NFC"));
    // no chunk boundary produced a leading combining mark in the emitted stream
    expect(/^[ً-ٰٟ]/u.test(out)).toBe(false);
  });

  it("passes plain English through intact", () => {
    const buf = new GraphemeBuffer();
    const out = buf.push("hello ") + buf.push("world") + buf.flush();
    expect(out).toBe("hello world");
  });
});

describe("textDirection — per-message dir resolution", () => {
  it("detects Arabic-leading text as rtl", () => {
    expect(textDirection("ما هو الحد الأدنى للرصيد؟")).toBe("rtl");
  });
  it("detects English-leading text as ltr", () => {
    expect(textDirection("What is KYC?")).toBe("ltr");
  });
  it("uses the first strong character for mixed text", () => {
    expect(textDirection("أبغى current account")).toBe("rtl");
    expect(textDirection("I want حساب جاري")).toBe("ltr");
  });
});
