import { splitUnits } from "@/three/lib/glyphAtlas";
import { describe, expect, it } from "vitest";

describe("splitUnits — Arabic shaping safety (§8.4a)", () => {
  it("keeps Arabic words whole (ligatures/joining preserved)", () => {
    const units = splitUnits("حساب التوفير");
    const arabic = units.filter((u) => u.script === "ar");
    expect(arabic.map((u) => u.text)).toEqual(["حساب", "التوفير"]);
  });

  it("splits Latin into graphemes for particle granularity", () => {
    const units = splitUnits("KYC");
    expect(units.map((u) => u.text)).toEqual(["K", "Y", "C"]);
    expect(units.every((u) => u.script === "en")).toBe(true);
  });

  it("tracks character offsets for token-cluster mapping", () => {
    const sentence = "فائدة 2.75% سنوياً";
    const units = splitUnits(sentence);
    for (const u of units) {
      expect(sentence.slice(u.start, u.end)).toBe(u.text);
    }
  });

  it("stays within the 1200-instance budget", () => {
    const long = Array.from({ length: 500 }, () => "word المصرف").join(" ");
    expect(splitUnits(long).length).toBeLessThanOrEqual(1200);
  });
});
