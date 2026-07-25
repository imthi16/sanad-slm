/**
 * Locale-aware number formatting (§8.6): Intl.NumberFormat per locale, with the settings
 * toggle for Eastern Arabic numerals in AR mode.
 *
 * "Eastern Arabic numerals" as used in the UAE are the standard Arabic-Indic digits
 * ٠١٢٣٤٥٦٧٨٩ = the CLDR `arab` numbering system (ar-u-nu-arab). CLDR `arabext` (۰۱۲۳…) is
 * the *extended* set used for Persian/Urdu — wrong digits for Gulf banking, so despite the
 * spec's example tag we ship `arab`.
 */

export type Numerals = "latn" | "arab";

export function numberLocale(lang: string, numerals: Numerals): string {
  if (lang === "ar") return numerals === "arab" ? "ar-u-nu-arab" : "ar-u-nu-latn";
  return "en";
}

export function formatNumber(
  value: number,
  lang: string,
  numerals: Numerals,
  options?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(numberLocale(lang, numerals), options).format(value);
}

/**
 * A measured figure for a table column. Fraction digits are pinned rather than capped: a
 * comparison column only reads as a column when the decimals line up, and ×1 beside ×1.65 makes
 * the cheapest row look like a different kind of number.
 */
export function formatMetric(
  value: number | null | undefined,
  lang: string,
  numerals: Numerals,
  digits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return formatNumber(value, lang, numerals, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatPercent(value: number, lang: string, numerals: Numerals): string {
  return new Intl.NumberFormat(numberLocale(lang, numerals), {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

export function shortSha(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 8) : "—";
}
