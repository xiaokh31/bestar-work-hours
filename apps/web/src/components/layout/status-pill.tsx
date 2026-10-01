type DashboardTone = "danger" | "info" | "neutral" | "success" | "warning";
export function StatusPill({
  label,
  tone = "neutral",
  title,
}: {
  label: string;
  tone?: DashboardTone;
  title?: string;
}) {
  return (
    <span
      className={[
        "status-pill inline-flex min-h-7 max-w-full items-center gap-1 border px-2.5 text-xs font-semibold leading-5 whitespace-normal",
        tonePillClass(tone),
      ].join(" ")}
      data-tone={tone}
      title={title}
    >
      <span aria-hidden="true" className="h-1.5 w-1.5 bg-current" />
      {label}
    </span>
  );
}

function tonePillClass(tone: DashboardTone): string {
  return {
    danger: "border-red-200 bg-red-50 text-red-800",
    info: "border-[var(--info-border)] bg-[var(--info-surface)] text-[var(--info-text)]",
    neutral: "border-zinc-200 bg-zinc-50 text-zinc-700",
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
    warning: "border-amber-200 bg-amber-50 text-amber-800",
  }[tone];
}
