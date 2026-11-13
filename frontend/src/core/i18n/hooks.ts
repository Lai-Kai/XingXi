"use client";

import { useI18nContext } from "./context";
import { DEFAULT_LOCALE } from "./locale";
import { translations } from "./translations";

export function useI18n() {
  const { locale, setLocale } = useI18nContext();

  const t = translations[locale] ?? translations[DEFAULT_LOCALE];

  return {
    locale,
    t,
    changeLocale: setLocale,
  };
}
