"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { DEFAULT_LOCALE, type Locale } from "../../lib/i18n/catalog";
import {
  createTranslator,
  normalizeLocale,
  type Translator,
} from "../../lib/i18n/translator";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Translator["t"];
  format: Translator["format"];
}

const defaultTranslator = createTranslator(DEFAULT_LOCALE);

const I18nContext = createContext<I18nContextValue>({
  locale: DEFAULT_LOCALE,
  setLocale: () => undefined,
  t: defaultTranslator.t,
  format: defaultTranslator.format,
});

export function I18nProvider({
  children,
  initialLocale,
}: {
  children: ReactNode;
  initialLocale: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(normalizeLocale(nextLocale));
  }, []);

  const translator = useMemo(() => createTranslator(locale), [locale]);
  const value = useMemo(
    () => ({ locale, setLocale, t: translator.t, format: translator.format }),
    [locale, setLocale, translator],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  return useContext(I18nContext);
}
