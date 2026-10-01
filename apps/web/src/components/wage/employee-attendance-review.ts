import type { AttendanceRowResponse } from "../../lib/api-client";
import {
  DEFAULT_LOCALE,
  type Locale,
  type MessageKey,
} from "../../lib/i18n/catalog";
import { createTranslator } from "../../lib/i18n/translator";

export type AttendanceCalculationMethod =
  | "LEGACY_UNKNOWN"
  | "NO_PUNCHES"
  | "FIRST_LAST_FALLBACK"
  | "PAIRED_INTERVALS";

export interface EmployeeAttendanceSummary {
  reviewDays: number;
  rowCount: number;
  totalCalculatedHours: number;
  workedDays: number;
}

export interface EmployeeAttendanceGroup {
  department: string | null;
  employeeId: string | null;
  employeeName: string | null;
  identityKey: string;
  rows: AttendanceRowResponse[];
  summary: EmployeeAttendanceSummary;
}

const CALCULATION_METHOD_MESSAGE_KEYS: Record<
  AttendanceCalculationMethod,
  MessageKey
> = {
  FIRST_LAST_FALLBACK: "First and last punch fallback",
  LEGACY_UNKNOWN: "Legacy calculation method",
  NO_PUNCHES: "No punches",
  PAIRED_INTERVALS: "Paired punch intervals",
};

const PARSER_VERSION_MESSAGE_KEYS: Record<string, MessageKey> = {
  "wage-attendance-v2": "Attendance calculation contract v2",
};

export function attendanceCalculationMethodLabel(
  method: string,
  locale: Locale = DEFAULT_LOCALE,
): string {
  const key = CALCULATION_METHOD_MESSAGE_KEYS[
    method as AttendanceCalculationMethod
  ];
  return createTranslator(locale).t(key ?? "Unknown calculation method");
}

export function attendanceParserVersionLabel(
  parserVersion: string | null,
  locale: Locale = DEFAULT_LOCALE,
): string {
  const key = parserVersion ? PARSER_VERSION_MESSAGE_KEYS[parserVersion] : undefined;
  return createTranslator(locale).t(key ?? "Legacy attendance calculation");
}

export function buildEmployeeAttendanceGroups(
  rows: AttendanceRowResponse[],
): EmployeeAttendanceGroup[] {
  const groups = new Map<
    string,
    Omit<EmployeeAttendanceGroup, "rows" | "summary"> & {
      rows: AttendanceRowResponse[];
    }
  >();

  for (const row of rows) {
    const identityKey = employeeAttendanceIdentityKey(row);
    const existing = groups.get(identityKey);
    if (existing) {
      existing.employeeId ??= cleanSourceText(row.employeeId);
      existing.employeeName ??= cleanSourceText(row.employeeName);
      existing.department ??= cleanSourceText(row.department);
      existing.rows.push(row);
      continue;
    }

    groups.set(identityKey, {
      department: cleanSourceText(row.department),
      employeeId: cleanSourceText(row.employeeId),
      employeeName: cleanSourceText(row.employeeName),
      identityKey,
      rows: [row],
    });
  }

  return [...groups.values()]
    .map((group) => {
      const sortedRows = [...group.rows].sort(compareAttendanceRows);
      return {
        ...group,
        rows: sortedRows,
        summary: summarizeEmployeeAttendance(sortedRows),
      };
    })
    .sort(compareEmployeeGroups);
}

export function employeeAttendanceIdentityKey(
  row: Pick<AttendanceRowResponse, "department" | "employeeId" | "employeeName">,
): string {
  const employeeId = normalizeIdentityPart(row.employeeId);
  if (employeeId) {
    return `id:${employeeId}`;
  }

  const employeeName = normalizeIdentityPart(row.employeeName);
  const department = normalizeIdentityPart(row.department);
  return `name:${employeeName || "unknown"}|department:${department || "unknown"}`;
}

export function summarizeEmployeeAttendance(
  rows: AttendanceRowResponse[],
): EmployeeAttendanceSummary {
  let reviewDays = 0;
  let totalHundredths = 0;
  let workedDays = 0;

  for (const row of rows) {
    const hours = decimalHundredths(row.calculatedHours);
    totalHundredths += hours;
    if (hours > 0) {
      workedDays += 1;
    }
    if (hasIssues(row.warnings) || hasIssues(row.errors)) {
      reviewDays += 1;
    }
  }

  return {
    reviewDays,
    rowCount: rows.length,
    totalCalculatedHours: totalHundredths / 100,
    workedDays,
  };
}

function cleanSourceText(value: string | null): string | null {
  const cleaned = value?.trim();
  return cleaned ? cleaned : null;
}

function normalizeIdentityPart(value: string | null): string {
  return value?.normalize("NFKC").trim().replace(/\s+/g, " ").toLocaleLowerCase() ?? "";
}

function compareAttendanceRows(
  left: AttendanceRowResponse,
  right: AttendanceRowResponse,
): number {
  return (
    left.workDate.localeCompare(right.workDate) ||
    left.dayNumber - right.dayNumber ||
    left.rowKey.localeCompare(right.rowKey) ||
    left.id.localeCompare(right.id)
  );
}

function compareEmployeeGroups(
  left: EmployeeAttendanceGroup,
  right: EmployeeAttendanceGroup,
): number {
  const leftName = normalizeIdentityPart(left.employeeName) || "\uffff";
  const rightName = normalizeIdentityPart(right.employeeName) || "\uffff";
  return (
    leftName.localeCompare(rightName) ||
    normalizeIdentityPart(left.employeeId).localeCompare(
      normalizeIdentityPart(right.employeeId),
    ) ||
    normalizeIdentityPart(left.department).localeCompare(
      normalizeIdentityPart(right.department),
    ) ||
    left.identityKey.localeCompare(right.identityKey)
  );
}

function hasIssues(input: unknown): boolean {
  return Array.isArray(input) && input.length > 0;
}

function decimalHundredths(value: string | null): number {
  if (value === null) {
    return 0;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}
