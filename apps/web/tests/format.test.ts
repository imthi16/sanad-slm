import { formatNumber, numberLocale } from "@/lib/format";
import { describe, expect, it } from "vitest";

describe("numerals (§8.6)", () => {
  it("uses Eastern Arabic numerals when toggled in AR mode", () => {
    expect(numberLocale("ar", "arab")).toBe("ar-u-nu-arab");
    expect(formatNumber(2.75, "ar", "arab")).toContain("٢");
  });

  it("keeps Western digits in AR mode by default", () => {
    expect(formatNumber(2.75, "ar", "latn")).toContain("2");
  });

  it("formats English locale plainly", () => {
    expect(formatNumber(1234.5, "en", "latn")).toBe("1,234.5");
  });
});
