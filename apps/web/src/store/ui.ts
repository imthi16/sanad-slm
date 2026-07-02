import { type Lang, applyLang } from "@/i18n";
import type { Numerals } from "@/lib/format";
import { create } from "zustand";

export type Mode = "dev" | "sovereign" | "edge";

interface UiState {
  lang: Lang;
  numerals: Numerals;
  mode: Mode; // refined from /v1/models meta at runtime
  reducedMotion: boolean;
  setLang: (lang: Lang) => void;
  setNumerals: (numerals: Numerals) => void;
  setMode: (mode: Mode) => void;
}

declare const __SANAD_MODE__: string;

export const useUiStore = create<UiState>((set) => ({
  lang: (localStorage.getItem("sanad.lang") as Lang) ?? "en",
  numerals: (localStorage.getItem("sanad.numerals") as Numerals) ?? "latn",
  mode: (typeof __SANAD_MODE__ !== "undefined" ? __SANAD_MODE__ : "dev") as Mode,
  reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  setLang: (lang) => {
    applyLang(lang);
    set({ lang });
  },
  setNumerals: (numerals) => {
    localStorage.setItem("sanad.numerals", numerals);
    set({ numerals });
  },
  setMode: (mode) => set({ mode }),
}));
