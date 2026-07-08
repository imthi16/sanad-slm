import { useTranslation } from "react-i18next";

export interface HeatCell {
  judge: string;
  dimension: string;
  mean_abs_dev: number;
}

/** judge × dimension disagreement heatmap (§5.4c) — CSS grid, no chart lib. */
export function AgreementHeatmap({ cells }: { cells: HeatCell[] }) {
  const { t } = useTranslation();
  const judges = [...new Set(cells.map((c) => c.judge))];
  const dims = [...new Set(cells.map((c) => c.dimension))];
  const max = Math.max(0.001, ...cells.map((c) => c.mean_abs_dev));

  const lookup = new Map(cells.map((c) => [`${c.judge}|${c.dimension}`, c.mean_abs_dev]));

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-1 text-xs">
        <caption className="sr-only">{t("evals.heatmap")}</caption>
        <thead>
          <tr>
            <th scope="col" className="text-start text-sand-400 font-normal p-1" />
            {dims.map((d) => (
              <th scope="col" key={d} className="text-sand-400 font-normal p-1">
                {t(`evals.judgeDims.${d}`, d)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {judges.map((j) => (
            <tr key={j}>
              <th scope="row" className="text-start text-sand-400 font-normal p-1" dir="ltr">
                {j}
              </th>
              {dims.map((d) => {
                const v = lookup.get(`${j}|${d}`) ?? 0;
                const intensity = v / max;
                return (
                  <td
                    key={d}
                    className="rounded p-2 text-center metric"
                    style={{
                      backgroundColor: `color-mix(in oklab, var(--color-claret-500) ${Math.round(
                        intensity * 65,
                      )}%, var(--color-dune-900))`,
                    }}
                    title={`${j} × ${d}: ${v.toFixed(2)}`}
                  >
                    {v.toFixed(2)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
