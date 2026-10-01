import type { Metadata } from "next";
import { cookies } from "next/headers";
import { I18nProvider } from "@/components/i18n/i18n-provider";
import {
  OfficeShell,
  type OfficeShellHealth,
} from "@/components/layout/office-shell";
import { getApiHealth } from "@/lib/api-client";
import { getBrandIconMetadata } from "@/lib/brand-assets";
import { getServerLocale } from "@/lib/i18n/server";
import { createTranslator } from "@/lib/i18n/translator";
import { getServerApiOptions } from "@/lib/server-api";
import {
  normalizeThemePreference,
  THEME_COOKIE_NAME,
} from "@/lib/theme";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const locale = await getServerLocale();
  const { t } = createTranslator(locale);

  return {
    title: `Bestar · ${t("Work Hours")}`,
    description: t("Work Hours"),
    icons: getBrandIconMetadata(),
  };
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const locale = await getServerLocale();
  const theme = normalizeThemePreference(cookieStore.get(THEME_COOKIE_NAME)?.value);
  const shellHealth = await getShellHealth();

  return (
    <html
      className="h-full antialiased"
      data-theme={theme}
      lang={locale}
      suppressHydrationWarning
    >
      <body className="min-h-full">
        <I18nProvider initialLocale={locale}>
          <OfficeShell
            health={shellHealth}
            locale={locale}
            theme={theme}
          >
            {children}
          </OfficeShell>
        </I18nProvider>
      </body>
    </html>
  );
}

async function getShellHealth(): Promise<OfficeShellHealth> {
  try {
    const health = await getApiHealth(await getServerApiOptions());
    return {
      apiStatus: health.status,
      databaseStatus: health.database?.status ?? "unknown",
      serverTime: health.serverTime,
      version: health.version,
    };
  } catch {
    return {
      apiStatus: "down",
      databaseStatus: "unknown",
      serverTime: new Date().toISOString(),
    };
  }
}
