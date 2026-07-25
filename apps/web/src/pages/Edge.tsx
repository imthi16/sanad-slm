import { Badge, Metric, Panel } from "@/components/ui";
import { formatMetric } from "@/lib/format";
import { subscribe } from "@/lib/sse";
import { useUiStore } from "@/store/ui";
import { EdgeBoard, type EdgeMetrics } from "@/three/EdgeBoard";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

interface Snapshot extends EdgeMetrics {
  source: string;
  ts: string;
  mem_used_gb: number | null;
}

const EMPTY: EdgeMetrics = {
  watts: null,
  temp_c: null,
  gpu_util_pct: null,
  tokens_per_second: null,
};

export default function Edge() {
  const { t } = useTranslation();
  const lang = useUiStore((s) => s.lang);
  const numerals = useUiStore((s) => s.numerals);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const sub = subscribe(
      "/v1/telemetry/stream",
      (data) => {
        try {
          setSnapshot(JSON.parse(data));
        } catch {
          // skip malformed frames
        }
      },
      setConnected,
    );
    return () => sub.close();
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl">{t("edge.title")}</h1>
          <p className="text-sm text-sand-400">{t("edge.sub")}</p>
        </div>
        <Badge tone={connected ? "live" : "alarm"} aria-live="polite">
          {snapshot?.source ?? t("edge.waiting")}
        </Badge>
      </div>

      <div className="panel h-[28rem] overflow-hidden">
        <EdgeBoard label={t("edge.canvasAlt")} metrics={snapshot ?? EMPTY} />
      </div>

      <Panel className="grid grid-cols-2 gap-4 md:grid-cols-5">
        <Metric
          label={t("edge.watts")}
          value={formatMetric(snapshot?.watts, lang, numerals)}
          unit="W"
        />
        <Metric
          label={t("edge.temp")}
          value={formatMetric(snapshot?.temp_c, lang, numerals)}
          unit="°C"
        />
        <Metric
          label={t("edge.gpuUtil")}
          value={formatMetric(snapshot?.gpu_util_pct, lang, numerals, 0)}
          unit="%"
        />
        <Metric
          label={t("edge.tokensPerSec")}
          value={formatMetric(snapshot?.tokens_per_second, lang, numerals)}
        />
        <Metric
          label={t("edge.memory")}
          value={formatMetric(snapshot?.mem_used_gb, lang, numerals)}
          unit="GB"
        />
      </Panel>
    </div>
  );
}
