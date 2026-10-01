"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useI18n } from "@/components/i18n/i18n-provider";
import {
  deleteAttendanceImport,
  getAttendanceImportDeletionImpact,
  type AttendanceImportDeletionImpactResponse,
  type AttendanceImportResponse,
} from "@/lib/api-client";
import { attendanceApiErrorMessage } from "./attendance-flow";

type DeleteStatus = "idle" | "loading" | "running" | "error";
const DELETE_STATUS = {
  error: "error",
  idle: "idle",
  loading: "loading",
  running: "running",
} as const;

export function AttendanceImportDeleteButton({
  attendanceImport,
  compact = false,
  isSelected,
}: {
  attendanceImport: AttendanceImportResponse;
  compact?: boolean;
  isSelected: boolean;
}) {
  const { format, locale, t } = useI18n();
  const router = useRouter();
  const searchParams = useSearchParams();
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const [open, setOpen] = useState(false);
  const [impact, setImpact] =
    useState<AttendanceImportDeletionImpactResponse | null>(null);
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<DeleteStatus>("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && status !== "running") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, status]);

  async function showImpact() {
    setOpen(true);
    setImpact(null);
    setMessage(t("Loading deletion impact."));
    setStatus(DELETE_STATUS.loading);
    try {
      const nextImpact = await getAttendanceImportDeletionImpact(
        attendanceImport.id,
      );
      setImpact(nextImpact);
      setMessage("");
      setStatus(DELETE_STATUS.idle);
      queueMicrotask(() => reasonRef.current?.focus());
    } catch (error) {
      setStatus(DELETE_STATUS.error);
      setMessage(attendanceApiErrorMessage(error, locale));
    }
  }

  async function submit() {
    if (status === "running") return;
    const normalizedReason = reason.trim();
    if (normalizedReason.length < 5) {
      setStatus(DELETE_STATUS.error);
      setMessage(t("Enter at least 5 characters for the deletion reason."));
      reasonRef.current?.focus();
      return;
    }
    setStatus(DELETE_STATUS.running);
    setMessage(t("Deleting attendance import."));
    try {
      const result = await deleteAttendanceImport(
        attendanceImport.id,
        normalizedReason,
      );
      const params = new URLSearchParams(searchParams.toString());
      params.set("notice", "import-deleted");
      if (isSelected) {
        params.delete("employeeKey");
        if (result.fallbackImport) {
          params.set("attendanceImportId", result.fallbackImport.id);
        } else {
          params.delete("attendanceImportId");
        }
      }
      setOpen(false);
      setReason("");
      setImpact(null);
      setStatus(DELETE_STATUS.idle);
      router.replace(`/work-hours${params.size ? `?${params.toString()}` : ""}`);
      router.refresh();
    } catch (error) {
      setStatus(DELETE_STATUS.error);
      setMessage(attendanceApiErrorMessage(error, locale));
    }
  }

  return (
    <>
      <button
        aria-label={format("i18n.workHours.deleteImportAria", {
          filename: attendanceImport.originalFilename,
        })}
        className={
          compact
            ? "inline-flex min-h-9 min-w-9 items-center justify-center border border-red-300 bg-white text-red-800 hover:bg-red-50"
            : "inline-flex min-h-10 items-center gap-2 border border-red-300 bg-white px-3 text-sm font-semibold text-red-800 hover:bg-red-50"
        }
        onClick={() => void showImpact()}
        title={t("Delete attendance import")}
        type="button"
      >
        <TrashIcon />
        {compact ? null : <span>{t("Delete import")}</span>}
      </button>
      {open ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/60 p-3 sm:p-4"
          onMouseDown={(event) => {
            if (
              event.target === event.currentTarget &&
              status !== "running"
            ) {
              setOpen(false);
            }
          }}
        >
          <section
            aria-describedby="attendance-import-delete-description"
            aria-labelledby="attendance-import-delete-title"
            aria-modal="true"
            className="max-h-[90vh] w-full max-w-2xl overflow-y-auto border border-zinc-300 bg-white p-4 shadow-2xl sm:p-6"
            role="dialog"
          >
            <h2
              className="break-words text-lg font-semibold text-zinc-950"
              id="attendance-import-delete-title"
            >
              {t("Remove this attendance import from active settlement?")}
            </h2>
            <p
              className="mt-2 text-sm leading-6 text-zinc-600"
              id="attendance-import-delete-description"
            >
              {t(
                "This batch will leave active settlement and downloads. The original workbook, parsed rows, generated files, jobs, and audit evidence remain preserved.",
              )}
            </p>
            {impact ? (
              <dl
                className="mt-4 grid gap-3 border border-zinc-200 bg-zinc-50 p-3 text-sm sm:grid-cols-2"
                data-testid="attendance-import-deletion-impact"
              >
                <ImpactItem
                  label={t("File")}
                  value={impact.originalFilename}
                />
                <ImpactItem
                  label={t("Period")}
                  value={
                    impact.settlementMonth ??
                    `${impact.periodStart ?? "-"} ${t("to")} ${impact.periodEnd ?? "-"}`
                  }
                />
                <ImpactItem
                  label={t("Attendance rows")}
                  value={format("i18n.workHours.importDeletionRows", {
                    active: impact.activeRowCount,
                    deleted: impact.deletedRowCount,
                  })}
                />
                <ImpactItem
                  label={t("Employees and days")}
                  value={format("i18n.workHours.importDeletionPeopleDays", {
                    employees: impact.employeeCount,
                    days: impact.dayCount,
                  })}
                />
                <ImpactItem
                  label={t("Generated files")}
                  value={String(impact.generatedFileCount)}
                />
                <ImpactItem
                  label={t("Issues")}
                  value={`${impact.warningCount} / ${impact.errorCount}`}
                />
              </dl>
            ) : null}
            <label
              className="mt-4 block text-sm font-semibold text-zinc-950"
              htmlFor={`delete-import-reason-${attendanceImport.id}`}
            >
              {t("Deletion reason")}
            </label>
            <textarea
              aria-describedby={`delete-import-reason-help-${attendanceImport.id}`}
              aria-invalid={status === "error" && reason.trim().length < 5}
              className="mt-2 min-h-28 w-full resize-y border border-zinc-300 px-3 py-2 text-sm text-zinc-950"
              disabled={status === "running" || status === "loading"}
              id={`delete-import-reason-${attendanceImport.id}`}
              maxLength={500}
              onChange={(event) => {
                setReason(event.target.value);
                if (status === "error") {
                  setMessage("");
                  setStatus(DELETE_STATUS.idle);
                }
              }}
              ref={reasonRef}
              value={reason}
            />
            <p
              className="mt-1 text-xs text-zinc-500"
              id={`delete-import-reason-help-${attendanceImport.id}`}
            >
              {format("i18n.workHours.deletionReasonLength", {
                count: reason.length,
              })}
            </p>
            <p
              aria-live="polite"
              className={`mt-2 min-h-5 text-sm ${
                status === "error" ? "text-red-800" : "text-zinc-600"
              }`}
              role={status === "error" ? "alert" : "status"}
            >
              {message}
            </p>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                className="min-h-10 border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950"
                disabled={status === "running"}
                onClick={() => setOpen(false)}
                type="button"
              >
                {t("Cancel")}
              </button>
              <button
                className="min-h-10 border border-red-700 bg-red-700 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-300"
                disabled={
                  status === "running" ||
                  status === "loading" ||
                  !impact
                }
                onClick={() => void submit()}
                type="button"
              >
                {status === "running" ? t("Deleting") : t("Delete import")}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}

function ImpactItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-zinc-500">{label}</dt>
      <dd className="break-words font-medium text-zinc-950">{value}</dd>
    </div>
  );
}

function TrashIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4 shrink-0"
      fill="none"
      viewBox="0 0 24 24"
    >
      <path
        d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.75"
      />
    </svg>
  );
}
