import { AgreementHeatmap, type HeatCell } from "@/components/evals/AgreementHeatmap";
import { Badge, Panel, Skeleton } from "@/components/ui";
import { formatMetric } from "@/lib/format";
import { getJson } from "@/lib/http";
import { useUiStore } from "@/store/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

interface RunListItem {
  id: string;
  created_at: string;
  model_version: string | null;
  headline: Record<string, number>;
}

interface RunDetail {
  id: string;
  provenance_split: Record<string, number> | null;
  benchmark_scores: Array<{
    task: string;
    model: string;
    metric: string;
    value: number;
    measured_locally: boolean;
  }>;
  judge: {
    headline_final: number;
    correct_rate: number;
    per_dimension: Array<{ dimension: string; score: number }>;
    judges: string[];
    human_judge_kappa: number | null;
  } | null;
  agreement: {
    krippendorff_alpha: Record<string, number | null>;
    pairwise_cohens_kappa: Record<string, number | null>;
    heatmap: HeatCell[];
    human_queue_count: number;
  } | null;
  efficiency: Record<string, number | null> | null;
}

export default function Evals() {
  const { t } = useTranslation();
  const lang = useUiStore((s) => s.lang);
  const numerals = useUiStore((s) => s.numerals);
  const [selected, setSelected] = useState<string | null>(null);

  const runs = useQuery({
    queryKey: ["eval-runs"],
    queryFn: () => getJson<RunListItem[]>("/v1/eval/runs"),
    staleTime: 60_000, // eval runs are slow-moving (§8.5)
  });

  const runId = selected ?? runs.data?.[0]?.id ?? null;
  const detail = useQuery({
    queryKey: ["eval-run", runId],
    queryFn: () => getJson<RunDetail>(`/v1/eval/runs/${runId}`),
    enabled: runId !== null,
    staleTime: 60_000,
  });

  const fmt = (v: number | null | undefined, digits = 2) => formatMetric(v, lang, numerals, digits);

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <h1 className="font-display text-2xl">{t("evals.title")}</h1>

      {runs.isLoading && <Skeleton className="h-24 w-full" />}
      {runs.data?.length === 0 && <Panel className="text-sand-400">{t("evals.noRuns")}</Panel>}

      {runs.data && runs.data.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-sand-400">{t("evals.selectRun")}</span>
          {runs.data.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setSelected(r.id)}
              className={`rounded-md border ps-3 pe-3 py-1 text-xs transition-colors duration-150 ${
                r.id === runId
                  ? "border-brass-400 text-brass-400"
                  : "border-dune-700 text-sand-400 hover:text-sand-100"
              }`}
              dir="ltr"
            >
              {r.id}
            </button>
          ))}
        </div>
      )}

      {detail.data && (
        <>
          <section className="grid gap-4 md:grid-cols-2">
            <Panel>
              <h2 className="mb-3 text-sm text-sand-400">{t("evals.benchmarks")}</h2>
              <table className="w-full text-sm">
                <tbody>
                  {detail.data.benchmark_scores.map((s) => (
                    <tr
                      key={`${s.task}-${s.model}-${s.metric}`}
                      className="border-t border-dune-700/60"
                    >
                      <td className="py-1.5 text-sand-400" dir="ltr">
                        {s.task}
                      </td>
                      <td className="py-1.5" dir="ltr">
                        {s.metric}
                      </td>
                      <td className="metric py-1.5 text-end">{fmt(s.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {detail.data.provenance_split && (
                <p className="mt-3 text-xs text-sand-400">
                  {t("evals.provenance")}:{" "}
                  <span className="metric" dir="ltr">
                    {Object.entries(detail.data.provenance_split)
                      .map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`)
                      .join(" · ")}
                  </span>
                </p>
              )}
            </Panel>

            <Panel>
              <h2 className="mb-3 text-sm text-sand-400">{t("evals.judge")}</h2>
              {detail.data.judge ? (
                <div className="space-y-3">
                  <div className="flex items-baseline gap-4">
                    <span className="metric text-3xl">{fmt(detail.data.judge.headline_final)}</span>
                    <span className="text-xs text-sand-400">/5</span>
                    <Badge tone={detail.data.judge.human_judge_kappa != null ? "teal" : "claret"}>
                      {detail.data.judge.human_judge_kappa != null
                        ? `${t("evals.humanKappa")}: ${fmt(detail.data.judge.human_judge_kappa)}`
                        : t("evals.humanKappaMissing")}
                    </Badge>
                  </div>
                  <div className="space-y-1.5">
                    {detail.data.judge.per_dimension.map((d) => (
                      <div key={d.dimension} className="flex items-center gap-2 text-xs">
                        <span className="w-28 text-sand-400">
                          {t(`evals.judgeDims.${d.dimension}`, d.dimension)}
                        </span>
                        <div className="h-2 flex-1 rounded-full bg-dune-700/50">
                          <div
                            className="h-2 rounded-full bg-teal-400"
                            style={{ inlineSize: `${(d.score / 5) * 100}%` }}
                          />
                        </div>
                        <span className="metric w-10 text-end">{fmt(d.score, 1)}</span>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-sand-400">
                    {t("evals.correctRate")}:{" "}
                    <span className="metric">{fmt(detail.data.judge.correct_rate * 100, 0)}%</span>
                  </p>
                </div>
              ) : (
                <p className="text-sm text-sand-400">{t("common.na")}</p>
              )}
            </Panel>
          </section>

          {detail.data.agreement && (
            <section className="grid gap-4 md:grid-cols-2">
              <Panel>
                <h2 className="mb-3 text-sm text-sand-400">{t("evals.agreement")}</h2>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="text-xs text-sand-400">{t("evals.alpha")}</div>
                    <div className="metric text-xl">
                      {fmt(detail.data.agreement.krippendorff_alpha.overall)}
                    </div>
                  </div>
                  {Object.entries(detail.data.agreement.pairwise_cohens_kappa).map(([pair, v]) => (
                    <div key={pair}>
                      <div className="text-xs text-sand-400" dir="ltr">
                        {pair}
                      </div>
                      <div className="metric text-xl">{fmt(v)}</div>
                    </div>
                  ))}
                </div>
              </Panel>
              <Panel>
                <h2 className="mb-3 text-sm text-sand-400">{t("evals.heatmap")}</h2>
                <AgreementHeatmap cells={detail.data.agreement.heatmap} />
              </Panel>
            </section>
          )}

          {detail.data.efficiency && (
            <Panel>
              <h2 className="mb-3 text-sm text-sand-400">{t("evals.efficiency")}</h2>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                {Object.entries(detail.data.efficiency).map(([k, v]) => (
                  <div key={k}>
                    <div className="text-xs text-sand-400" dir="ltr">
                      {k}
                    </div>
                    <div className="metric text-lg">{fmt(v)}</div>
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
