"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useI18n } from "@/components/i18n/i18n-provider";
import { isOfficeNavItemActive } from "./office-navigation-flow";

export interface OfficeNavItem {
  href: string;
  label: string;
}

export function OfficeNavigation({
  items,
  variant = "top",
}: {
  items: OfficeNavItem[];
  variant?: "rail" | "top";
}) {
  const pathname = usePathname();
  const { t } = useI18n();

  return (
    <nav
      aria-label={t("Office navigation")}
      className={[
        "flex gap-1",
        variant === "rail" ? "flex-col" : "overflow-x-auto",
      ].join(" ")}
    >
      {items.map((item) => (
        <Link
          aria-current={isOfficeNavItemActive(pathname, item.href) ? "page" : undefined}
          className={navItemClassName(
            variant,
            isOfficeNavItemActive(pathname, item.href),
          )}
          href={item.href}
          key={item.href}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}

function navItemClassName(variant: "rail" | "top", active: boolean): string {
  if (variant === "rail") {
    return [
      "flex min-h-10 items-center border-l-4 px-3 text-sm font-semibold transition-colors",
      active
        ? "border-[var(--forklift-amber)] bg-white/10 text-white"
        : "border-transparent text-zinc-200 hover:border-zinc-500 hover:bg-white/5 hover:text-white",
    ].join(" ");
  }

  return [
    "flex min-h-11 items-center whitespace-nowrap border-b-2 px-3 text-sm font-semibold transition-colors",
    active
      ? "border-[var(--forklift-amber)] text-white"
      : "border-transparent text-zinc-100 hover:border-zinc-300 hover:text-white",
  ].join(" ");
}
