import {
  DEFAULT_LOCALE,
  LOCALE_MESSAGES,
  SAME_TEXT_MESSAGE_KEYS,
  SUPPORTED_LOCALES,
  type Locale,
  type MessageKey,
} from "./catalog";

export interface Translator {
  locale: Locale;
  t: (key: MessageKey) => string;
  format: (key: MessageKey, params: TranslationParams) => string;
}

export type TranslationParams = Readonly<Record<string, string | number>>;

export class MissingTranslationError extends Error {
  readonly key: string;
  readonly locale: Locale;

  constructor(key: string, locale: Locale) {
    super(`Missing ${locale} translation for message key: ${key}`);
    this.name = "MissingTranslationError";
    this.key = key;
    this.locale = locale;
  }
}

export function isSupportedLocale(value: string | null | undefined): value is Locale {
  return SUPPORTED_LOCALES.includes(value as Locale);
}

export function normalizeLocale(value: string | null | undefined): Locale {
  if (isSupportedLocale(value)) {
    return value;
  }

  if (value?.toLowerCase().startsWith("zh")) {
    return "zh-CN";
  }

  return DEFAULT_LOCALE;
}

/** Creates the explicit translation interface used by rendered Web UI. */
export function createTranslator(locale: Locale): Translator {
  const normalizedLocale = normalizeLocale(locale);
  const t = (key: MessageKey) => {
    const value = LOCALE_MESSAGES[normalizedLocale][key];

    if (value && hasResolvedTranslation(key, normalizedLocale)) {
      return value;
    }

    return handleMissingTranslation(key, normalizedLocale);
  };

  return {
    locale: normalizedLocale,
    t,
    format(key, params) {
      return formatTranslationTemplate(t(key), params);
    },
  };
}

export function formatTranslationTemplate(
  template: string,
  params: TranslationParams,
): string {
  return template.replace(/\{([A-Za-z0-9_]+)\}/g, (placeholder, name: string) => {
    const value = params[name];
    return value === undefined ? placeholder : String(value);
  });
}

function hasResolvedTranslation(key: MessageKey, locale: Locale): boolean {
  return (
    locale !== "zh-CN" ||
    LOCALE_MESSAGES[locale][key] !== LOCALE_MESSAGES.en[key] ||
    SAME_TEXT_MESSAGE_KEYS.includes(key as (typeof SAME_TEXT_MESSAGE_KEYS)[number])
  );
}

function handleMissingTranslation(key: string, locale: Locale): string {
  const error = new MissingTranslationError(key, locale);

  if (process.env.NODE_ENV !== "production") {
    throw error;
  }

  console.error(error);
  return LOCALE_MESSAGES[locale]["Translation unavailable"];
}
