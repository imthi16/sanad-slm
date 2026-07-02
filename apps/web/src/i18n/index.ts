import i18next from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./ar/common.json";
import en from "./en/common.json";

export type Lang = "en" | "ar";

export const i18n = i18next.createInstance();

i18n.use(initReactI18next).init({
  resources: {
    en: { common: en },
    ar: { common: ar },
  },
  lng: (localStorage.getItem("sanad.lang") as Lang) ?? "en",
  fallbackLng: "en",
  defaultNS: "common",
  interpolation: { escapeValue: false },
  returnNull: false,
});

/** Flip <html dir lang> — the single global bidi switch (§8.3, §8.6). */
export function applyLang(lang: Lang): void {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  localStorage.setItem("sanad.lang", lang);
  void i18n.changeLanguage(lang);
}

// apply persisted choice on boot
applyLang((i18n.language as Lang) ?? "en");
