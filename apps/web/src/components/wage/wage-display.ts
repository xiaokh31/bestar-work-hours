import {
  DEFAULT_LOCALE,
  type Locale,
  type MessageKey,
} from "../../lib/i18n/catalog";
import { businessStatusLabel } from "../../lib/i18n/status-labels";
import { createTranslator } from "../../lib/i18n/translator";

export interface StatusStyle {
  label: string;
  styles: string;
}

export function statusStyle(status: string, locale?: Locale): StatusStyle {
  const normalized = status.toUpperCase();
  if (
    normalized === "READY" ||
    normalized === "GENERATED" ||
    normalized === "COMPLETED" ||
    normalized === "UPLOADED" ||
    normalized === "PARSED"
  ) {
    return {
      label: businessStatusLabel(status, locale),
      styles: "border-emerald-200 bg-emerald-50 text-emerald-800",
    };
  }
  if (
    normalized === "WARNING" ||
    normalized === "NEEDS_REVIEW" ||
    normalized === "DRAFT" ||
    normalized === "NOT_PARSED"
  ) {
    return {
      label: businessStatusLabel(status, locale),
      styles: "border-amber-200 bg-amber-50 text-amber-800",
    };
  }
  if (
    normalized === "ERROR" ||
    normalized === "FAILED" ||
    normalized === "CANCELLED"
  ) {
    return {
      label: businessStatusLabel(status, locale),
      styles: "border-red-200 bg-red-50 text-red-800",
    };
  }
  if (normalized === "SETTLED" || normalized === "SUPERSEDED") {
    return {
      label: businessStatusLabel(status, locale),
      styles: "border-zinc-300 bg-zinc-100 text-zinc-800",
    };
  }
  return {
    label: businessStatusLabel(status, locale),
    styles: "border-zinc-200 bg-zinc-50 text-zinc-700",
  };
}

export function issueList(
  input: unknown,
  locale: Locale = DEFAULT_LOCALE,
): string[] {
  if (!Array.isArray(input)) {
    return [];
  }

  return input.map((item) => wageIssueMessage(item, locale));
}

const WAGE_ISSUE_MESSAGE_KEYS: Record<string, MessageKey> = {
  ATTENDANCE_PERIOD_MISSING: "Attendance period is missing.",
  DETECTOR_ERROR: "Attendance workbook could not be parsed.",
  DETECTOR_WARNING: "Attendance workbook needs parser review.",
  MISSING_DEPARTMENT: "Employee department is missing.",
  MISSING_EMPLOYEE_ID: "Employee ID is missing.",
  MISSING_EMPLOYEE_NAME: "Employee name is missing.",
  MISSING_PUNCH_TIMES: "No usable punch times found for employee-day.",
  ODD_PUNCH_COUNT:
    "Odd punch count requires manual review before calculating hours.",
  WAGE_RECORD_GENERATION_FAILED: "Wage record generation failed.",
  WAGE_TEMPLATE_DATE_ROWS_NOT_FOUND:
    "Wage template date rows were not found.",
  WAGE_TEMPLATE_EMPLOYEE_NOT_MATCHED:
    "Attendance employee was not matched to a wage template sheet.",
};

function wageIssueMessage(input: unknown, locale: Locale): string {
  const { t } = createTranslator(locale);
  if (input && typeof input === "object") {
    const code = (input as Record<string, unknown>).code;
    if (typeof code === "string" && WAGE_ISSUE_MESSAGE_KEYS[code]) {
      return t(WAGE_ISSUE_MESSAGE_KEYS[code]);
    }
  }

  return t("Review issue details are unavailable.");
}

export function formatMoney(amount: string | number, currency = "CAD"): string {
  const parsed = Number(amount);
  if (!Number.isFinite(parsed)) {
    return `${currency} ${String(amount)}`;
  }

  return `${currency} ${parsed.toFixed(2)}`;
}

export function formatDateOnly(value: string | null): string {
  if (!value) {
    return "-";
  }
  return value.slice(0, 10);
}

export function formatDateTime(
  value: string | null,
  locale: Locale = DEFAULT_LOCALE,
): string {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(locale === "zh-CN" ? "zh-CN" : "en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatUnknownList(input: unknown): string {
  if (Array.isArray(input)) {
    return input.map((item) => String(item)).join(", ");
  }
  if (typeof input === "string") {
    return input;
  }
  if (input === null || input === undefined) {
    return "-";
  }
  return JSON.stringify(input);
}
