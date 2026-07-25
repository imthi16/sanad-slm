import { Specimen } from "@/components/fertility/Specimen";
import { TokenizerLedger } from "@/components/fertility/TokenizerLedger";
import { useTokenizerStore } from "@/store/tokenizer";
import { FertilityField } from "@/three/FertilityField";
import { PipelineOrbit } from "@/three/PipelineOrbit";
import { useFertility } from "@/three/lib/useTokenClusters";
import { useState } from "react";
import { useTranslation } from "react-i18next";

/** Legend for the Specimen's rule — the dash colours mean script, so they need naming. */
function ScriptLegend() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      <span className="flex items-center gap-2">
        <span className="h-[3px] w-6 bg-sand-100" aria-hidden />
        <span className="eyebrow">{t("fertility.legendAr")}</span>
      </span>
      <span className="flex items-center gap-2">
        <span className="h-[3px] w-6 bg-pewter-400" aria-hidden />
        <span className="eyebrow">{t("fertility.legendEn")}</span>
      </span>
      <span className="eyebrow text-sand-400/70">{t("fertility.legendUnit")}</span>
    </div>
  );
}

/**
 * The results table. Values stay em-dashed until a report exists to back them (prime
 * directive 5), and the "traces to" column is the point of the table rather than filler.
 */
function ResultsLedger() {
  const { t } = useTranslation();
  const rows = [
    { key: "results.strip.domain", unit: "pts" },
    { key: "results.strip.arabicmmlu", unit: "pts" },
    { key: "results.strip.cost", unit: "USD" },
    { key: "results.strip.edge", unit: "tok/s" },
  ] as const;

  return (
    <section className="rule-top">
      <div className="mx-auto max-w-6xl px-6 py-14">
        <p className="eyebrow">{t("results.eyebrow")}</p>
        <h2 className="font-display mt-2 text-3xl">{t("results.title")}</h2>
        <p className="mt-3 max-w-[58ch] text-sm text-sand-400">{t("results.note")}</p>

        <div className="mt-8">
          <div
            className="grid grid-cols-[1fr_auto] gap-x-6 border-b border-ink-700 pb-1.5
                       sm:grid-cols-[1fr_7rem_auto]"
          >
            <span className="eyebrow">{t("results.metric")}</span>
            <span className="eyebrow text-end">{t("results.value")}</span>
            <span className="eyebrow hidden text-end sm:block">{t("results.tracesTo")}</span>
          </div>
          {rows.map(({ key, unit }) => (
            <div
              key={key}
              className="grid grid-cols-[1fr_auto] items-baseline gap-x-6 border-b
                         border-ink-700/60 py-3 sm:grid-cols-[1fr_7rem_auto]"
            >
              <span className="text-sm text-sand-300">{t(key)}</span>
              <span className="text-end">
                <span className="unmeasured text-lg">—</span>{" "}
                <span className="text-xs text-sand-400" dir="ltr">
                  {unit}
                </span>
              </span>
              <span
                className="eyebrow col-span-2 pt-1 text-sand-400/70 sm:col-span-1 sm:pt-0
                           sm:text-end"
              >
                {t("results.pending")}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Home() {
  const { t } = useTranslation();
  const text = useTokenizerStore((s) => s.text);
  const setText = useTokenizerStore((s) => s.setText);
  const selected = useTokenizerStore((s) => s.selected);
  const result = useTokenizerStore((s) => s.result);
  const { measure } = useFertility();
  const [fieldOpen, setFieldOpen] = useState(false);

  const segments = result?.tokenizers[selected]?.segments ?? [];

  return (
    <div>
      <section className="mx-auto max-w-6xl px-6 pt-14 pb-10">
        <p className="eyebrow">{t("hero.eyebrow")}</p>
        <h1 className="font-display text-display mt-4 max-w-[24ch]">{t("hero.headline")}</h1>
        <p className="mt-6 max-w-[58ch] text-sand-400">{t("hero.sub")}</p>
      </section>

      {/* The specimen sits on the page ground rather than inside a card: it is the artefact
          being examined, and a border would make it one panel among several. */}
      <section className="rule-top bg-ink-900/70">
        <div className="mx-auto max-w-6xl px-6 py-12">
          <Specimen text={text} segments={segments} className="pb-4" />

          {/* The field spans the full measure: the specimen it edits is a long bilingual
              sentence, and a narrow input clips the far end of whichever script loses. */}
          <div className="mt-8 flex flex-col gap-6 border-t border-ink-700 pt-6">
            <ScriptLegend />
            <label className="flex w-full flex-col gap-2 sm:flex-row sm:items-baseline sm:gap-5">
              <span className="eyebrow shrink-0">{t("hero.editSentence")}</span>
              <input
                dir="auto"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onBlur={() => measure(text)}
                onKeyDown={(e) => e.key === "Enter" && measure(text)}
                placeholder={t("fertility.tryPlaceholder")}
                className="w-full min-w-0 flex-1 border-b border-ink-600 bg-transparent pb-1.5 font-mono text-sm
                           text-sand-100 transition-colors duration-150
                           placeholder:text-sand-400/50 focus:border-verdigris-400
                           focus:outline-none"
              />
            </label>
          </div>
        </div>
      </section>

      <section className="rule-top">
        <div className="mx-auto grid max-w-6xl gap-10 px-6 py-12 md:grid-cols-[minmax(0,1fr)_17rem]">
          <TokenizerLedger />
          <aside className="flex flex-col gap-4">
            <p className="text-sm text-sand-400">{t("fertility.insight")}</p>
            <button
              type="button"
              onClick={() => setFieldOpen((open) => !open)}
              aria-expanded={fieldOpen}
              className="eyebrow self-start border-b border-ink-600 pb-1 text-sand-300
                         transition-colors duration-150 hover:border-verdigris-400
                         hover:text-sand-100"
            >
              {fieldOpen ? t("fertility.hideFieldView") : t("fertility.fieldView")}
            </button>
          </aside>
        </div>
        {fieldOpen ? (
          <div className="mx-auto max-w-6xl px-6 pb-12">
            <div className="h-[24rem]">
              <FertilityField label={t("hero.canvasAlt")} />
            </div>
          </div>
        ) : null}
      </section>

      <ResultsLedger />

      <section className="rule-top">
        <div className="mx-auto max-w-6xl px-6 py-14">
          <p className="eyebrow">{t("pipeline.eyebrow")}</p>
          <h2 className="font-display mt-2 text-3xl">{t("pipeline.title")}</h2>
          <p className="mt-3 max-w-[58ch] text-sm text-sand-400">{t("pipeline.sub")}</p>
          <div className="mt-8 h-96 overflow-hidden">
            <PipelineOrbit label={t("pipeline.title")} />
          </div>
        </div>
      </section>
    </div>
  );
}
