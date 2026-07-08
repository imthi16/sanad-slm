import { Panel } from "@/components/ui";
import { formatMetric } from "@/lib/format";
import { TOKENIZER_ORDER, useTokenizerStore } from "@/store/tokenizer";
import { useUiStore } from "@/store/ui";
import { FertilityField } from "@/three/FertilityField";
import { PipelineOrbit } from "@/three/PipelineOrbit";
import { useFertility } from "@/three/lib/useTokenClusters";
import { clsx } from "clsx";
import { useTranslation } from "react-i18next";

function TokenizerPills() {
  const { t } = useTranslation();
  const selected = useTokenizerStore((s) => s.selected);
  const select = useTokenizerStore((s) => s.select);
  return (
    // single-select modelled as toggle buttons (aria-pressed) — no fake radio roles
    <div aria-label={t("fertility.tokenizer")} className="flex flex-wrap gap-2">
      {TOKENIZER_ORDER.map((name) => (
        <button
          key={name}
          type="button"
          aria-pressed={selected === name}
          onClick={() => select(name)}
          className={clsx(
            "rounded-full border ps-3 pe-3 py-1 text-xs transition-colors duration-150",
            selected === name
              ? "border-brass-400 text-brass-400"
              : "border-dune-700 text-sand-400 hover:text-sand-100",
          )}
          dir="ltr"
        >
          {name}
        </button>
      ))}
    </div>
  );
}

function FertilityHud() {
  const { t } = useTranslation();
  const lang = useUiStore((s) => s.lang);
  const numerals = useUiStore((s) => s.numerals);
  const selected = useTokenizerStore((s) => s.selected);
  const result = useTokenizerStore((s) => s.result);
  const tok = result?.tokenizers[selected];
  return (
    <div className="flex items-center gap-6 text-sm" aria-live="polite">
      <span>
        <span className="metric text-xl">
          {tok ? formatMetric(tok.tokens, lang, numerals, 0) : "—"}
        </span>{" "}
        <span className="text-sand-400">{t("fertility.tokens")}</span>
      </span>
      <span>
        <span className="metric text-xl">
          {tok ? formatMetric(tok.tokens_per_word, lang, numerals, 2) : "—"}
        </span>{" "}
        <span className="text-sand-400">{t("fertility.tokensPerWord")}</span>
      </span>
      <span>
        <span className="metric text-xl">
          {tok?.cost_vs_best ? `×${formatMetric(tok.cost_vs_best, lang, numerals, 2)}` : "—"}
        </span>{" "}
        <span className="text-sand-400">{t("fertility.costVsBest")}</span>
      </span>
    </div>
  );
}

function ResultsStrip() {
  const { t } = useTranslation();
  // Headline numbers land here from ml/evals/reports at P4 — each must trace to a report
  // file by hash (working agreement #6). Placeholders render as em-dashes, never fake values.
  const items = [
    { key: "results.strip.domain", value: null, unit: "pts" },
    { key: "results.strip.arabicmmlu", value: null, unit: "pts" },
    { key: "results.strip.cost", value: null, unit: "USD" },
    { key: "results.strip.edge", value: null, unit: "tok/s" },
  ] as const;
  return (
    <section className="mx-auto grid max-w-6xl grid-cols-2 gap-3 p-4 md:grid-cols-4">
      {items.map(({ key, value, unit }) => (
        <Panel key={key} className="text-center">
          <div className="metric text-2xl">{value ?? "—"}</div>
          <div className="text-xs text-sand-400">
            {t(key)} <span dir="ltr">({unit})</span>
          </div>
        </Panel>
      ))}
    </section>
  );
}

export default function Home() {
  const { t } = useTranslation();
  const text = useTokenizerStore((s) => s.text);
  const setText = useTokenizerStore((s) => s.setText);
  const { measure } = useFertility();

  return (
    <div>
      <section className="mx-auto max-w-6xl p-4">
        <div className="py-8">
          <h1 className="font-display text-display max-w-3xl">{t("hero.headline")}</h1>
          <p className="mt-4 max-w-2xl text-sand-400">{t("hero.sub")}</p>
        </div>

        <div className="panel overflow-hidden">
          <div className="h-[26rem]">
            <FertilityField label={t("hero.canvasAlt")} />
          </div>
          <div className="flex flex-col gap-3 border-t border-dune-700 p-4">
            <label className="flex flex-col gap-2">
              <span className="text-xs text-sand-400">{t("hero.editSentence")}</span>
              <input
                dir="auto"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onBlur={() => measure(text)}
                onKeyDown={(e) => e.key === "Enter" && measure(text)}
                placeholder={t("fertility.tryPlaceholder")}
                className="w-full rounded-md border border-dune-700 bg-dune-950 px-3 py-2 text-sm
                           text-sand-100 placeholder:text-sand-400/60"
              />
            </label>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <TokenizerPills />
              <FertilityHud />
            </div>
            <p className="text-xs text-sand-400">{t("fertility.insight")}</p>
          </div>
        </div>
      </section>

      <ResultsStrip />

      <section className="mx-auto max-w-6xl p-4">
        <h2 className="font-display mb-3 text-2xl">{t("pipeline.title")}</h2>
        <div className="panel h-96 overflow-hidden">
          <PipelineOrbit label={t("pipeline.title")} />
        </div>
      </section>
    </div>
  );
}
