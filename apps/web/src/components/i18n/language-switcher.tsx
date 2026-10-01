"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import {
  LOCALE_LABELS,
  SUPPORTED_LOCALES,
  type Locale,
  type MessageKey,
} from "@/lib/i18n/catalog";
import { persistBrowserLocale } from "@/lib/i18n/browser";
import { useI18n } from "./i18n-provider";

export function LanguageSwitcher() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const { locale, setLocale, t } = useI18n();

  function switchLocale(option: Locale) {
    if (option === locale) {
      return;
    }

    // The cookie remains the SSR source of truth. Update Client Components immediately,
    // then refresh the Server Component payload without discarding local form state.
    persistBrowserLocale(option);
    setLocale(option);
    startTransition(() => router.refresh());
  }

  return (
    <div
      aria-label={t("Language")}
      aria-busy={isPending}
      className="inline-flex min-h-9 overflow-hidden border border-white/20 bg-black/10 text-xs font-semibold"
    >
      {SUPPORTED_LOCALES.map((option) => (
        <button
          aria-pressed={locale === option}
          className={[
            "min-h-9 px-3 transition-colors",
            locale === option
              ? "bg-white text-[var(--surface-action-foreground)]"
              : "text-zinc-100 hover:bg-white/10",
          ].join(" ")}
          disabled={isPending}
          key={option}
          onClick={() => switchLocale(option)}
          type="button"
        >
          {t(LOCALE_LABELS[option] as MessageKey)}
        </button>
      ))}
    </div>
  );
}
