export const THEME_COOKIE_NAME = "bestar_theme";

export const THEME_OPTIONS = ["light", "dark", "system"] as const;

export type ThemePreference = (typeof THEME_OPTIONS)[number];

export type ResolvedTheme = Exclude<ThemePreference, "system">;

export function normalizeThemePreference(value: string | undefined): ThemePreference {
  return THEME_OPTIONS.includes(value as ThemePreference)
    ? (value as ThemePreference)
    : "system";
}

export function resolveTheme(
  preference: ThemePreference,
  systemTheme: ResolvedTheme,
): ResolvedTheme {
  return preference === "system" ? systemTheme : preference;
}

export function themeColorScheme(theme: ThemePreference): string {
  return theme === "system" ? ["light", "dark"].join(" ") : theme;
}

export function themeCookieValue(cookieHeader: string): ThemePreference | null {
  const prefix = `${THEME_COOKIE_NAME}=`;
  for (const part of cookieHeader.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      try {
        return normalizeThemePreference(
          decodeURIComponent(trimmed.slice(prefix.length)),
        );
      } catch {
        return "system";
      }
    }
  }
  return null;
}

export function persistBrowserTheme(theme: ThemePreference): void {
  if (typeof document === "undefined") return;
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${THEME_COOKIE_NAME}=${theme}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
}
