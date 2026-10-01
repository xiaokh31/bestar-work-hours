import { enMessages } from "./locales/en";
import { zhMessages } from "./locales/zh";

export const SUPPORTED_LOCALES = ["en", "zh-CN"] as const;

export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";

export const LOCALE_COOKIE_NAME = "bestar_locale";

export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  "zh-CN": "中文",
};

export const LOCALE_MESSAGES = {
  en: enMessages,
  "zh-CN": zhMessages,
} as const;

export type MessageKey = keyof typeof enMessages;

// These identifiers, brands, and language names intentionally remain identical
// across the supported office locales.
export const SAME_TEXT_MESSAGE_KEYS = [
  "0 B",
  "Bestar Service CCA",
  "English",
  "SHA-256",
  "UTC",
  "中文",
] as const satisfies readonly MessageKey[];
