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

  if (mode === "sovereign") return <Badge tone="live">{t("badge.sovereign")}</Badge>;
  if (mode === "edge") return <Badge tone="live">{t("badge.edge")}</Badge>;
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
      className="border-b border-ink-600 pb-0.5 text-sm text-sand-300 transition-colors
                 duration-150 hover:border-verdigris-400 hover:text-sand-100"
      lang={lang === "en" ? "ar" : "en"}
    >
      {t("lang.toggle")}
    </button>
  );
}

/**
 * The wordmark carries both scripts at all times, in the two display faces — the one permanent
 * place on the site where the dual-script pairing is stated rather than demonstrated. Explicit
 * `lang` on each half keeps Ruqaa on the Arabic and Fraunces on the Latin whichever way the
 * interface is currently set.
 */
function Wordmark() {
  return (
    <NavLink to="/" className="flex items-baseline gap-2.5">
      <span lang="ar" className="font-display text-[2.4rem] leading-none text-sand-100">
        سَنَد
      </span>
      <span aria-hidden className="h-4 w-px self-center bg-ink-600" />
      <span
        lang="en"
        dir="ltr"
        className="font-display text-sm leading-none tracking-[0.22em] text-sand-400"
      >
        SANAD
      </span>
    </NavLink>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="min-h-dvh flex flex-col">
      <a href="#main" className="skip-link">
        {t("nav.skipToContent")}
      </a>
      <header className="sticky top-0 z-50 border-b border-ink-700 bg-ink-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-8 px-6 py-3">
          <Wordmark />
          <nav aria-label="primary" className="flex min-w-0 items-center gap-5 overflow-x-auto">
            {NAV.map(({ to, key }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `whitespace-nowrap border-b pb-0.5 text-sm transition-colors duration-150 ${
                    isActive
                      ? "border-verdigris-400 text-sand-100"
                      : "border-transparent text-sand-400 hover:text-sand-100"
                  }`
                }
              >
                {t(key)}
              </NavLink>
            ))}
          </nav>
          <div className="ms-auto flex shrink-0 items-center gap-4">
            <SovereignBadge />
            <LangToggle />
          </div>
        </div>
      </header>
      <main id="main" className="flex-1">
        {children}
      </main>
      <footer className="rule-top mt-4">
        <div
          className="mx-auto flex max-w-6xl flex-col gap-2 px-6 py-6 text-xs text-sand-400
                     sm:flex-row sm:items-center sm:justify-between"
        >
          <span>{t("app.tagline")}</span>
          <span className="flex items-center gap-4">
            <span className="font-mono" dir="ltr">
              {t("footer.cost")}
            </span>
            <span className="font-mono" dir="ltr">
              {t("footer.license")}
            </span>
          </span>
        </div>
      </footer>
    </div>
  );
}
