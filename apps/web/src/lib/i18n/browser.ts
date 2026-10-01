import { LOCALE_COOKIE_NAME, type Locale } from "./catalog";
import { normalizeLocale } from "./translator";

const LOCAL_STORAGE_KEY = "bestar.locale";

export function readBrowserLocale(): Locale | null {
  if (typeof window === "undefined") {
    return null;
  }

  const cookieLocale = readLocaleCookie(document.cookie);
  if (cookieLocale) {
    return cookieLocale;
  }

  return normalizeLocale(window.navigator.language);
}

export function persistBrowserLocale(locale: Locale): void {
  if (typeof document === "undefined") {
    return;
  }

  window.localStorage.setItem(LOCAL_STORAGE_KEY, locale);
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = [
    `${LOCALE_COOKIE_NAME}=${encodeURIComponent(locale)}`,
    "Path=/",
    "Max-Age=31536000",
    "SameSite=Lax",
    secure,
  ]
    .filter(Boolean)
    .join("; ");
}

export function readLocaleCookie(cookieHeader: string): Locale | null {
  const prefix = `${LOCALE_COOKIE_NAME}=`;
  for (const part of cookieHeader.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return normalizeLocale(decodeURIComponent(trimmed.slice(prefix.length)));
    }
  }
  return null;
}
