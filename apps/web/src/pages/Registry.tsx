import { Badge, Panel, Skeleton } from "@/components/ui";
import { shortSha } from "@/lib/format";
import { getJson } from "@/lib/http";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

interface ArtifactItem {
  model_name: string;
  version: string;
  sha256: string | null;
  cosign_signed: boolean;
  licenses: string[];
  base_model: string | null;
  created_at: string | null;
}

interface RegistryResponse {
  artifacts: ArtifactItem[];
  lineage: {
    nodes: Array<{ id: string; kind: string; cosign_signed?: boolean }>;
    edges: Array<{ from: string; to: string; label: string }>;
  };
}

export default function Registry() {
  const { t } = useTranslation();
  const registry = useQuery({
    queryKey: ["registry"],
    queryFn: () => getJson<RegistryResponse>("/v1/registry/artifacts"),
    staleTime: 120_000,
  });

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div>
        <h1 className="font-display text-2xl">{t("registry.title")}</h1>
        <p className="text-sm text-sand-400">{t("registry.sub")}</p>
      </div>

      {registry.isLoading && <Skeleton className="h-40 w-full" />}
      {registry.data?.artifacts.length === 0 && (
        <Panel className="text-sand-400">{t("registry.empty")}</Panel>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {registry.data?.artifacts.map((a) => (
          <Panel key={`${a.model_name}@${a.version}`} className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="font-display" dir="ltr">
                {a.model_name}
                <span className="text-brass-400 ms-1">@{a.version}</span>
              </span>
              <Badge tone={a.cosign_signed ? "teal" : "claret"}>
                {a.cosign_signed ? t("registry.signed") : t("registry.unsigned")}
              </Badge>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
              <dt className="text-sand-400">{t("registry.base")}</dt>
              <dd dir="ltr">{a.base_model ?? "—"}</dd>
              <dt className="text-sand-400">{t("registry.sha")}</dt>
              <dd className="metric" dir="ltr">
                {shortSha(a.sha256)}
              </dd>
              <dt className="text-sand-400">{t("registry.license")}</dt>
              <dd dir="ltr">{a.licenses.join(", ") || "—"}</dd>
            </dl>
            {/* lineage chain for this version, rendered from the graph */}
            <LineageChain registry={registry.data} id={`${a.model_name}@${a.version}`} />
          </Panel>
        ))}
      </div>
    </div>
  );
}

function LineageChain({ registry, id }: { registry: RegistryResponse | undefined; id: string }) {
  if (!registry) return null;
  const incoming = registry.lineage.edges.filter((e) => e.to === id);
  const outgoing = registry.lineage.edges.filter((e) => e.from === id);
  if (incoming.length === 0 && outgoing.length === 0) return null;
  return (
    <div
      className="flex flex-wrap items-center gap-1.5 border-t border-dune-700/60 pt-2 text-xs"
      dir="ltr"
    >
      {incoming.map((e) => (
        <span key={`${e.from}-${e.to}`} className="text-sand-400">
          <span className="text-teal-400">{e.from}</span> →
        </span>
      ))}
      <span className="text-brass-400">{id}</span>
      {outgoing.map((e) => (
        <span key={`${e.from}-${e.to}`} className="text-sand-400">
          → <span className="text-teal-400">{e.to}</span>
        </span>
      ))}
    </div>
  );
}
