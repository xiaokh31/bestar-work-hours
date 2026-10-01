"use client";

import { useEffect, useState } from "react";
import {
  THEME_OPTIONS,
  persistBrowserTheme,
  themeColorScheme,
  type ThemePreference,
} from "@/lib/theme";
import type { MessageKey } from "@/lib/i18n/catalog";
import type { Translator } from "@/lib/i18n/translator";
import { useI18n } from "@/components/i18n/i18n-provider";

const themeIcon: Record<ThemePreference, string> = {
  light: "☀",
  dark: "◐",
  system: "◉",
};

const themeShortLabels: Record<ThemePreference, MessageKey> = {
  dark: "Dark",
  light: "Light",
  system: "System",
};

const themeActionLabels: Record<ThemePreference, MessageKey> = {
  dark: "Dark theme",
  light: "Light theme",
  system: "Follow system theme",
};

export function ThemeControl({
  initialTheme,
}: {
  initialTheme: ThemePreference;
}) {
  const { t } = useI18n();
  const [theme, setTheme] = useState(initialTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  function changeTheme(nextTheme: ThemePreference) {
    if (nextTheme === theme) return;
    setTheme(nextTheme);
    persistBrowserTheme(nextTheme);
  }

  return (
    <div aria-label={t("Theme")} className="theme-control" role="group">
      {THEME_OPTIONS.map((option) => (
        <ThemeOption
          key={option}
          onClick={() => changeTheme(option)}
          option={option}
          selected={theme === option}
          t={t}
        />
      ))}
    </div>
  );
}

function ThemeOption({
  onClick,
  option,
  selected,
  t,
}: {
  onClick: () => void;
  option: ThemePreference;
  selected: boolean;
  t: Translator["t"];
}) {
  const shortLabel = t(themeShortLabels[option]);
  const actionLabel = t(themeActionLabels[option]);

  return (
    <button
      aria-label={actionLabel}
      aria-pressed={selected}
      className="theme-control-button"
      data-tooltip={shortLabel}
      onClick={onClick}
      title={shortLabel}
      type="button"
    >
      <span aria-hidden="true">{themeIcon[option]}</span>
      <span className="sr-only">{shortLabel}</span>
    </button>
  );
}

function applyTheme(theme: ThemePreference) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = themeColorScheme(theme);
}
