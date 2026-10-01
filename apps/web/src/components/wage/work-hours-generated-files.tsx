
import {
  getAttendanceGeneratedFileDownloadUrl,
  type WageGeneratedFileResponse,
} from "../../lib/api-client";
import type { Locale } from "../../lib/i18n/catalog";
import { generatedFileTypeLabel } from "../../lib/i18n/status-labels";
import { createTranslator } from "../../lib/i18n/translator";
import {
  generatedFileAuditText,
  officeVisibleWageFiles,
} from "./attendance-flow";
import { formatDateTime, statusStyle } from "./wage-display";

export function WorkHoursGeneratedFiles({
  attendanceImportId,
  files,
  locale,
}: {
  attendanceImportId: string;
  files: readonly WageGeneratedFileResponse[];
  locale: Locale;
}) {
  const { t } = createTranslator(locale);
  const visibleFiles = officeVisibleWageFiles(files);

  if (visibleFiles.length === 0) {
    return (
      <p className="mt-4 border border-dashed border-zinc-300 bg-zinc-50 p-4 text-sm text-zinc-600">
        {t("No wage record files yet.")}
      </p>
    );
  }

  return (
    <div className="mt-4 grid gap-3">
      {visibleFiles.map((file) => (
        <GeneratedFileLink
          attendanceImportId={attendanceImportId}
          file={file}
          key={file.id}
          locale={locale}
        />
      ))}
    </div>
  );
}

function GeneratedFileLink({
  attendanceImportId,
  file,
  locale,
}: {
  attendanceImportId: string;
  file: WageGeneratedFileResponse;
  locale: Locale;
}) {
  const { t } = createTranslator(locale);
  const downloadable = ["READY", "GENERATED"].includes(file.status);
  const status = statusStyle(file.status, locale);

  return (
    <div
      className="border border-zinc-200 bg-zinc-50 p-3"
      data-testid="wage-record-file"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-zinc-950">
            {generatedFileTypeLabel(file.fileType, locale)}
          </p>
          <p className="mt-1 text-xs text-zinc-500">
            {formatDateTime(file.updatedAt, locale)}
          </p>
        </div>
        <span
          className={`inline-flex min-h-7 items-center rounded border px-2.5 text-xs font-semibold uppercase ${status.styles}`}
          title={status.label}
        >
          {status.label}
        </span>
      </div>
      <p className="mt-3 break-all text-xs leading-5 text-zinc-600">
        {generatedFileAuditText(file, locale)}
      </p>
      {downloadable ? (
        <a download
          className="mt-3 inline-flex min-h-9 items-center border border-teal-700 bg-white px-3 text-xs font-semibold uppercase text-teal-800 hover:bg-teal-50"
          href={getAttendanceGeneratedFileDownloadUrl(attendanceImportId, file.id)}
        >
          {t("Download")}
        </a>
      ) : file.errorMessage ? (
        <p className="mt-3 text-sm text-red-800">
          {t("Generated wage file failed. Review the job result and try again.")}
        </p>
      ) : null}
    </div>
  );
}
