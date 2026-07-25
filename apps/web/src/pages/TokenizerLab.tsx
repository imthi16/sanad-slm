import { Panel } from "@/components/ui";
import { formatMetric } from "@/lib/format";
import { TOKENIZER_ORDER, useTokenizerStore } from "@/store/tokenizer";
import { useUiStore } from "@/store/ui";
import { useFertility } from "@/three/lib/useTokenClusters";
import { useTranslation } from "react-i18next";

/** 2D detail view of the hero data (§8.3): segment chips + fertility table. */
export default function TokenizerLab() {
  const { t } = useTranslation();
  const lang = useUiStore((s) => s.lang);
  const numerals = useUiStore((s) => s.numerals);
  const setNumerals = useUiStore((s) => s.setNumerals);
  const text = useTokenizerStore((s) => s.text);
  const setText = useTokenizerStore((s) => s.setText);
  const result = useTokenizerStore((s) => s.result);
  const { measure, loading } = useFertility();

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div>
        <h1 className="font-display text-2xl">{t("tokenizerlab.title")}</h1>
        <p className="text-sm text-sand-400">{t("tokenizerlab.sub")}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          dir="auto"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => measure(text)}
          onKeyDown={(e) => e.key === "Enter" && measure(text)}
          placeholder={t("fertility.tryPlaceholder")}
          className="min-w-0 flex-1 rounded-md border border-ink-700 bg-ink-900 px-3 py-2.5
                     text-sm text-sand-100 placeholder:text-sand-400/60"
        />
        <label className="flex items-center gap-2 text-xs text-sand-400">
          <input
            type="checkbox"
            checked={numerals === "arab"}
            onChange={(e) => setNumerals(e.target.checked ? "arab" : "latn")}
            className="accent-verdigris-400"
          />
          {t("numerals.label")}
        </label>
      </div>

      <Panel>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-start text-xs text-sand-400">
              <th className="py-2 text-start font-normal">{t("fertility.tokenizer")}</th>
              <th className="py-2 text-end font-normal">{t("fertility.tokens")}</th>
              <th className="py-2 text-end font-normal">{t("fertility.tokensPerWord")}</th>
              <th className="py-2 text-end font-normal">{t("fertility.costVsBest")}</th>
            </tr>
          </thead>
          <tbody aria-busy={loading}>
            {TOKENIZER_ORDER.map((name) => {
              const tok = result?.tokenizers[name];
              return (
                <tr key={name} className="border-t border-ink-700/60">
                  <td className="py-2" dir="ltr">
                    {name}
                  </td>
                  <td className="metric py-2 text-end">
                    {formatMetric(tok?.tokens ?? null, lang, numerals, 0)}
                  </td>
                  <td className="metric py-2 text-end">
                    {formatMetric(tok?.tokens_per_word ?? null, lang, numerals, 2)}
                  </td>
                  <td className="metric py-2 text-end">
                    {tok?.cost_vs_best
                      ? `×${formatMetric(tok.cost_vs_best, lang, numerals, 2)}`
                      : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Panel>

      <section className="space-y-3">
        <h2 className="text-sm text-sand-400">{t("tokenizerlab.segments")}</h2>
        {TOKENIZER_ORDER.map((name) => {
          const tok = result?.tokenizers[name];
          if (!tok) return null;
          return (
            <Panel key={name}>
              <div className="mb-2 text-xs text-sand-400" dir="ltr">
                {name} · {tok.tokens} {t("fertility.tokens")}
              </div>
              <div dir="auto" className="flex flex-wrap gap-1">
                {tok.segments.map((s, i) => (
                  <span
                    // biome-ignore lint/suspicious/noArrayIndexKey: segments are positional
                    key={i}
                    className={`bidi-isolate rounded px-1.5 py-0.5 text-sm ${
                      s.script === "ar"
                        ? "bg-verdigris-400/15 text-verdigris-400"
                        : "bg-sand-400/10 text-sand-100"
                    }`}
                    title={`#${s.id}`}
                  >
                    {s.text}
                  </span>
                ))}
              </div>
            </Panel>
          );
        })}
      </section>
    </div>
  );
}
