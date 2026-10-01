import type { ReactNode } from "react";
import { BrandLogo } from "@/components/brand/brand-logo";
import { StatusPill } from "@/components/layout/status-pill";
import { LanguageSwitcher } from "@/components/i18n/language-switcher";
import { OperationalClock } from "@/components/layout/operational-clock";
import { ThemeControl } from "@/components/layout/theme-control";
import { OPERATIONAL_TIME_ZONE_LABEL } from "@/lib/date-time";
import type { Locale } from "@/lib/i18n/catalog";
import type { ThemePreference } from "@/lib/theme";
import { healthStatusLabel } from "@/lib/i18n/status-labels";
import { createTranslator } from "@/lib/i18n/translator";

export interface OfficeShellHealth {
  apiStatus: "degraded" | "down" | "ok";
  databaseStatus: "down" | "unknown" | "up";
  version?: string;
  serverTime: string;
}

export function OfficeShell({
  children,
  health,
  locale,
  theme,
}: {
  children: ReactNode;
  health: OfficeShellHealth;
  locale: Locale;
  theme: ThemePreference;
}) {
  const { t } = createTranslator(locale);

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <div className="min-h-screen min-w-0" data-office-shell-content="true">
        <header className="sticky top-0 z-30 border-b border-[var(--line-soft)] bg-[var(--dock-steel)] text-white shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6 lg:px-8">
            <div className="min-w-0" data-shell-brand="top">
              <BrandLogo
                accessibility="meaningful"
                accessibleName="Bestar Service CCA"
                locale={locale}
                preload
                responsiveCompact
                variant="onDark"
              />
              <p className="font-control mt-2 text-sm font-semibold text-zinc-200">
                {t("Work Hours")}
              </p>
            </div>
            <div
              className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-2"
              data-shell-actions="true"
            >
              <OperationalStatus health={health} locale={locale} />
              <ThemeControl initialTheme={theme} />
              <LanguageSwitcher />
            </div>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}

function OperationalStatus({
  health,
  locale,
}: {
  health: OfficeShellHealth;
  locale: Locale;
}) {
  const { t } = createTranslator(locale);
  const apiTone = health.apiStatus === "ok" ? "success" : "warning";
  const databaseTone = health.databaseStatus === "up" ? "success" : "danger";
  return (
    <div className="hidden flex-wrap items-center gap-2 xl:flex">
      <div className="border border-white/10 bg-white/5 px-3 py-2 text-xs">
        <p className="font-semibold text-zinc-300">
          {t("Operational time")}
        </p>
        <OperationalClock initialIso={health.serverTime} />
      </div>
      <div className="border border-white/10 bg-white/5 px-3 py-2 text-xs">
        <p className="font-semibold text-zinc-300">{t("Time zone")}</p>
        <p className="font-data mt-1" data-i18n-ignore="true">
          {OPERATIONAL_TIME_ZONE_LABEL}
        </p>
      </div>
      <StatusPill
        label={healthStatusLabel(health.apiStatus, locale)}
        title={t("API status")}
        tone={apiTone}
      />
      <StatusPill
        label={healthStatusLabel(health.databaseStatus, locale)}
        title={t("Database status")}
        tone={databaseTone}
      />
    </div>
  );
}
