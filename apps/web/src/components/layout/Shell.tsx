import { Badge } from "@/components/ui";
import { getJson } from "@/lib/http";
import { type Mode, useUiStore } from "@/store/ui";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router-dom";

interface ModelsMeta {
  data: Array<{ id: string; x_sanad?: { mode?: Mode } }>;
}

const NAV = [
  { to: "/", key: "nav.home" },
  { to: "/chat", key: "nav.chat" },
  { to: "/evals", key: "nav.evals" },
  { to: "/tokenizer", key: "nav.tokenizer" },
  { to: "/edge", key: "nav.edge" },
  { to: "/registry", key: "nav.registry" },
] as const;

function SovereignBadge() {
  const { t } = useTranslation();
  const mode = useUiStore((s) => s.mode);
  const setMode = useUiStore((s) => s.setMode);

  // the badge reads /v1/models meta (§8.3) — server truth beats build-time define
  useQuery({
    queryKey: ["models-meta"],
    queryFn: async () => {
      const res = await getJson<ModelsMeta>("/v1/models");
      const serverMode = res.data[0]?.x_sanad?.mode;
      if (serverMode) setMode(serverMode);
      return res;
    },
    staleTime: 60_000,
    retry: 1,
  });

  if (mode === "sovereign") return <Badge tone="teal">{t("badge.sovereign")}</Badge>;
  if (mode === "edge") return <Badge tone="teal">{t("badge.edge")}</Badge>;
  return <Badge tone="sand">{t("badge.dev")}</Badge>;
}

function LangToggle() {
  const { t } = useTranslation();
  const lang = useUiStore((s) => s.lang);
  const setLang = useUiStore((s) => s.setLang);
  return (
    <button
      type="button"
      onClick={() => setLang(lang === "en" ? "ar" : "en")}
      aria-label={t("lang.toggleAria")}
      className="rounded-md border border-dune-700 ps-3 pe-3 py-1.5 text-sm text-sand-100
                 hover:border-brass-400/60 transition-colors duration-150"
      lang={lang === "en" ? "ar" : "en"}
    >
      {t("lang.toggle")}
    </button>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="min-h-dvh flex flex-col">
      <a href="#main" className="skip-link">
        {t("nav.skipToContent")}
      </a>
      <header className="sticky top-0 z-50 border-b border-dune-700 bg-dune-950/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-6 p-3">
          <NavLink to="/" className="font-display text-xl tracking-tight text-sand-100">
            {t("app.title")}
            <span className="text-brass-400">.</span>
          </NavLink>
          <nav aria-label="primary" className="flex items-center gap-1 overflow-x-auto">
            {NAV.map(({ to, key }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `rounded-md ps-3 pe-3 py-1.5 text-sm transition-colors duration-150 ${
                    isActive ? "text-brass-400" : "text-sand-400 hover:text-sand-100"
                  }`
                }
              >
                {t(key)}
              </NavLink>
            ))}
          </nav>
          <div className="ms-auto flex items-center gap-3">
            <SovereignBadge />
            <LangToggle />
          </div>
        </div>
      </header>
      <main id="main" className="flex-1">
        {children}
      </main>
      <footer className="border-t border-dune-700 py-4 text-center text-xs text-sand-400">
        {t("app.tagline")}
      </footer>
    </div>
  );
}
