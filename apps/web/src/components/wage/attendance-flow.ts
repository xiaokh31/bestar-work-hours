import type {
  AttendanceImportResponse,
  WageGeneratedFileResponse,
} from "@/lib/api-client";
import {
  DEFAULT_LOCALE,
  type Locale,
  type MessageKey,
} from "../../lib/i18n/catalog";
import { createTranslator } from "../../lib/i18n/translator";

export interface FileLike {
  name: string;
  size?: number;
}

export const OFFICE_VISIBLE_WAGE_FILE_TYPES = ["WAGE_RECORD_XLS"] as const;

export type OfficeVisibleWageFileType =
  (typeof OFFICE_VISIBLE_WAGE_FILE_TYPES)[number];

const officeVisibleWageFileTypes = new Set<string>(
  OFFICE_VISIBLE_WAGE_FILE_TYPES,
);

export function isOfficeVisibleWageFile(
  file: { fileType?: string | null },
): file is { fileType: OfficeVisibleWageFileType } {
  return (
    typeof file.fileType === "string" &&
    officeVisibleWageFileTypes.has(file.fileType)
  );
}

export function officeVisibleWageFiles<
  T extends { fileType?: string | null },
>(files: readonly T[]): T[] {
  return files.filter(isOfficeVisibleWageFile);
}

export function isAllowedLegacyXlsFile(file: FileLike): boolean {
  return file.name.trim().toLowerCase().endsWith(".xls");
}

export function attendanceUploadError(
  file: FileLike | null,
  locale: Locale = DEFAULT_LOCALE,
): string | null {
  const { t } = createTranslator(locale);

  if (!file) {
    return t("Select one legacy .xls attendance workbook.");
  }

  if (!isAllowedLegacyXlsFile(file)) {
    return t("Attendance imports must use the legacy .xls time-clock workbook.");
  }

  if (file.size !== undefined && file.size > 3_000_000) return t("The workbook exceeds the upload limit (3 MB).");
  return null;
}

export function formatHours(value: string | number | null): string {
  if (value === null || value === "") {
    return "-";
  }

  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return String(value);
  }

  return parsed.toFixed(2);
}

export function canGenerateWageRecord(
  attendanceImport: Pick<
    AttendanceImportResponse,
    "errorCount" | "parseStatus"
  >,
): boolean {
  const parseStatus = attendanceImport.parseStatus.toUpperCase();
  return (
    (parseStatus === "PARSED" || parseStatus === "WARNING") &&
    attendanceImport.errorCount === 0
  );
}

export function wageGenerationBlockReason(
  attendanceImport: Pick<
    AttendanceImportResponse,
    "errorCount" | "parseStatus"
  >,
  locale: Locale = DEFAULT_LOCALE,
): string | null {
  const { t } = createTranslator(locale);

  if (canGenerateWageRecord(attendanceImport)) {
    return null;
  }

  const parseStatus = attendanceImport.parseStatus.toUpperCase();
  if (parseStatus === "NOT_PARSED" || parseStatus === "PARSING") {
    return t("Parse this attendance import before generating a wage record.");
  }

  return t("Parser errors must be resolved before generating a wage record.");
}

export function formatFileSize(value: string | null): string {
  if (!value) {
    return "-";
  }

  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) {
    return value;
  }

  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function generatedFileAuditText(
  file: Pick<
    WageGeneratedFileResponse,
    "fileSha256" | "fileSizeBytes" | "mimeType"
  >,
  locale: Locale = DEFAULT_LOCALE,
): string {
  return createTranslator(locale).format("i18n.workHours.generatedFileAudit", {
    mimeType: file.mimeType ?? "-",
    sha256: file.fileSha256 ?? "-",
    size: formatFileSize(file.fileSizeBytes),
  });
}

export function attendanceApiErrorMessage(
  error: unknown,
  locale: Locale = DEFAULT_LOCALE,
): string {
  const { t } = createTranslator(locale);
  const messages: Record<string, MessageKey> = {
    ATTENDANCE_FILE_TOO_LARGE: "The workbook exceeds the upload limit (3 MB).",
    UNSUPPORTED_ATTENDANCE_FILE: "The workbook format is invalid.",
    UNAUTHORIZED: "Work hours service connection is not configured correctly.",
    ATTENDANCE_FILE_EMPTY: "Attendance workbook is empty.",
    ATTENDANCE_FILE_REQUIRED: "Select one legacy .xls attendance workbook.",
    ATTENDANCE_FILE_TYPE_UNSUPPORTED:
      "Attendance imports must use the legacy .xls time-clock workbook.",
    ATTENDANCE_IMPORT_HAS_PARSE_ERRORS:
      "Attendance import has parser errors and cannot generate a wage record.",
    ATTENDANCE_IMPORT_NOT_FOUND: "Attendance import could not be found.",
    ATTENDANCE_IMPORT_NOT_PARSED:
      "Attendance import must be parsed before generating a wage record.",
    ATTENDANCE_IMPORT_BUSY:
      "Attendance parsing or wage generation is running. Try again after it finishes.",
    ATTENDANCE_IMPORT_DELETED:
      "This attendance import was deleted. Showing the next active import.",
    ATTENDANCE_ROW_NOT_FOUND:
      "Attendance row could not be found in the selected import.",
    ATTENDANCE_DATA_REVISION_CHANGED:
      "Attendance data changed during generation. Generate the wage record again.",
    ATTENDANCE_ROW_AUDIT_INCONSISTENT:
      "Attendance deletion audit is inconsistent. Contact an administrator.",
    ATTENDANCE_IMPORT_AUDIT_INCONSISTENT:
      "Attendance import deletion audit is inconsistent. Contact an administrator.",
    ATTENDANCE_ORIGINAL_FILE_MISSING:
      "Original attendance workbook is unavailable.",
    ATTENDANCE_PARSE_FAILED:
      "Attendance parse failed. Review parser errors before generating a wage record.",
    ATTENDANCE_ACTIVE_ROWS_REQUIRED:
      "No active employee-day rows are available. Parse the attendance workbook again before retrying.",
    ATTENDANCE_WORKER_INVOCATION_FAILED:
      "Attendance parse failed. Review parser errors before generating a wage record.",
    DUPLICATE_ATTENDANCE_IMPORT:
      "Duplicate attendance upload: this workbook already exists by SHA-256.",
    FORBIDDEN: "Open the app using its configured address and try again.",
    WAGE_RECORD_GENERATION_FAILED:
      "Wage record generation failed. Review generated file history for the failed record.",
    WAGE_RECORD_WORKER_INVOCATION_FAILED:
      "Wage record generation failed. Review generated file history for the failed record.",
    WORKER_ATTENDANCE_TIMEOUT:
      "Wage generation timed out. Retry once; contact an administrator if it happens again.",
    WORKER_ATTENDANCE_EMPTY_OUTPUT:
      "The wage generator returned no result. Retry once; contact an administrator if it happens again.",
    WORKER_ATTENDANCE_INVALID_OUTPUT:
      "The wage generator returned an invalid result. Contact an administrator.",
    WORKER_ATTENDANCE_INVOCATION_FAILED:
      "The wage generator could not start. Contact an administrator.",
    WAGE_GENERATION_INPUT_SCHEMA_INVALID:
      "Saved attendance data is incompatible with wage generation. Parse the attendance workbook again.",
    WAGE_GENERATION_WORKER_SCHEMA_INVALID:
      "The wage generator version is incompatible. Contact an administrator.",
    WAGE_GENERATION_PERIOD_MISSING:
      "The attendance period is missing. Parse the attendance workbook again.",
    WAGE_GENERATION_PERIOD_MISMATCH:
      "The generated workbook period did not match the attendance month. Contact an administrator.",
    WAGE_TEMPLATE_MISSING:
      "The wage workbook template is unavailable. Contact an administrator.",
    WAGE_TEMPLATE_UNREADABLE:
      "The wage workbook template could not be opened. Contact an administrator.",
    WAGE_TEMPLATE_SHA_MISMATCH:
      "The approved wage workbook template failed its integrity check. Contact an administrator.",
    WAGE_TEMPLATE_VERSION_MISMATCH:
      "The approved wage workbook template failed its integrity check. Contact an administrator.",
    WAGE_TEMPLATE_PRIVACY_AUDIT_FAILED:
      "The approved wage workbook template failed its integrity check. Contact an administrator.",
    WAGE_TEMPLATE_METADATA_NOT_CLEARED:
      "The approved wage workbook template failed its integrity check. Contact an administrator.",
    WAGE_TEMPLATE_SHEET_COUNT_INVALID:
      "The approved wage workbook template failed its integrity check. Contact an administrator.",
    WAGE_TEMPLATE_EMPLOYEE_SLOT_COUNT_INVALID:
      "The approved wage workbook template failed its integrity check. Contact an administrator.",
    WAGE_TEMPLATE_FORMULA_COUNT_INVALID:
      "The approved wage workbook template failed its integrity check. Contact an administrator.",
    WAGE_TEMPLATE_MERGE_COUNT_INVALID:
      "The approved wage workbook template failed its integrity check. Contact an administrator.",
    WAGE_TEMPLATE_XF_COUNT_INVALID:
      "The approved wage workbook template failed its integrity check. Contact an administrator.",
    WAGE_TEMPLATE_NOT_READ_ONLY:
      "The approved wage workbook template is not safely installed. Contact an administrator.",
    WAGE_TEMPLATE_EMPLOYEE_CAPACITY_EXCEEDED:
      "The attendance employee count exceeds the approved workbook capacity. Contact an administrator.",
    WAGE_TEMPLATE_CHANGED_DURING_GENERATION:
      "The wage workbook template changed during generation. Retry the generation.",
    WAGE_GENERATION_ZERO_EFFECTIVE_OUTPUT:
      "No employees could be written to the wage workbook. Review employee-template matching.",
    WAGE_GENERATION_SAVE_FAILED:
      "The wage workbook could not be saved. Retry once; contact an administrator if it happens again.",
    WAGE_GENERATION_OUTPUT_VALIDATION_FAILED:
      "The generated wage workbook failed validation and was not published. Retry the generation.",
    WAGE_GENERATION_MANIFEST_INVALID:
      "The generated wage workbook failed its audit check and was not published. Retry the generation.",
    WAGE_GENERATION_STORAGE_PATH_INVALID:
      "The generated wage workbook failed its storage safety check. Contact an administrator.",
  };

  return t(
    isApiErrorLike(error)
      ? (messages[error.code] ?? "The request failed.")
      : "The request failed.",
  );
}

function isApiErrorLike(
  error: unknown,
): error is { code: string; message: string; status?: number } {
  return Boolean(
    error &&
      typeof error === "object" &&
      "code" in error &&
      "message" in error &&
      typeof (error as { code: unknown }).code === "string" &&
      typeof (error as { message: unknown }).message === "string",
  );
}
