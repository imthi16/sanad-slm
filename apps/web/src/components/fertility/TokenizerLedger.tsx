/**
 * The ledger under the Specimen: all five tokenizers priced at once (ADR-0005).
 *
 * The earlier hero made you click through pills one at a time and read a single HUD, so the
 * comparison lived in your memory. Here every row is measured on the same sentence
 * simultaneously and the cheapest is marked, so the Arabic tax is a column you read rather than
 * a sequence you remember. Selection only chooses which row the Specimen's rule illustrates.
 */
import { formatMetric, formatNumber } from "@/lib/format";
import { TOKENIZER_ORDER, useTokenizerStore } from "@/store/tokenizer";
import { useUiStore } from "@/store/ui";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

export function TokenizerLedger() {
  const { t } = useTranslation();
  const lang = useUiStore((s) => s.lang);
  const numerals = useUiStore((s) => s.numerals);
  const selected = useTokenizerStore((s) => s.selected);
  const select = useTokenizerStore((s) => s.select);
  const result = useTokenizerStore((s) => s.result);

  const rows = TOKENIZER_ORDER.map((name) => ({ name, tok: result?.tokenizers[name] }));
  const cheapest = rows.reduce<{ name: string; value: number } | null>((best, { name, tok }) => {
    if (!tok) return best;
    return !best || tok.tokens_per_word < best.value ? { name, value: tok.tokens_per_word } : best;
  }, null);

  return (
    <fieldset className="min-w-0">
      <legend className="sr-only">{t("fertility.tokenizer")}</legend>
      <div
        className="grid grid-cols-[1fr_3.2rem_4.5rem] items-end gap-x-3 border-b
                   border-ink-700 pb-1.5 sm:grid-cols-[1fr_4rem_5rem_4.5rem]"
      >
        <span className="eyebrow">{t("fertility.tokenizer")}</span>
        <span className="eyebrow text-end">{t("fertility.tokens")}</span>
        <span className="eyebrow text-end">{t("fertility.tokensPerWord")}</span>
        <span className="eyebrow hidden text-end sm:block">{t("fertility.costVsBest")}</span>
      </div>

      {rows.map(({ name, tok }) => {
        const isSelected = selected === name;
        const isCheapest = cheapest?.name === name;
        return (
          <button
            key={name}
            type="button"
            aria-pressed={isSelected}
            onClick={() => select(name)}
            className={clsx(
              "grid w-full grid-cols-[1fr_3.2rem_4.5rem] items-center gap-x-3 border-s-2",
              "sm:grid-cols-[1fr_4rem_5rem_4.5rem]",
              "border-b border-b-ink-700/60 py-2 text-start transition-colors",
              "duration-150 hover:bg-ink-900",
              isSelected ? "border-s-verdigris-400 bg-ink-900" : "border-s-transparent",
            )}
          >
            <span className="flex flex-wrap items-baseline gap-x-2 ps-2.5">
              <span
                dir="ltr"
                className={clsx(
                  "font-mono text-sm",
                  isSelected ? "text-sand-100" : "text-sand-300",
                )}
              >
                {name}
              </span>
              {isCheapest ? (
                <span className="eyebrow text-verdigris-400">{t("fertility.cheapest")}</span>
              ) : null}
            </span>
            <span className={clsx("text-end text-sm", tok ? "metric" : "unmeasured")}>
              {tok ? formatNumber(tok.tokens, lang, numerals) : "—"}
            </span>
            <span className={clsx("text-end text-sm", tok ? "metric" : "unmeasured")}>
              {tok ? formatMetric(tok.tokens_per_word, lang, numerals, 2) : "—"}
            </span>
            <span
              className={clsx(
                "hidden text-end text-sm sm:block",
                tok?.cost_vs_best ? "metric" : "unmeasured",
              )}
            >
              {tok?.cost_vs_best ? `×${formatMetric(tok.cost_vs_best, lang, numerals, 2)}` : "—"}
            </span>
          </button>
        );
      })}

      {result ? null : <p className="pt-2 text-xs text-sand-400">{t("fertility.notMeasured")}</p>}
    </fieldset>
  );
}
