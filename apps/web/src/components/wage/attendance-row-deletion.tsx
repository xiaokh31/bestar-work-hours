"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/components/i18n/i18n-provider";
import {
  deleteAttendanceRow,
  type AttendanceRowResponse,
} from "@/lib/api-client";
import { attendanceApiErrorMessage, formatHours } from "./attendance-flow";

const DELETE_STATUS = {
  error: "error",
  idle: "idle",
  running: "running",
} as const;

export function AttendanceRowDeleteButton({
  attendanceImportId,
  row,
}: {
  attendanceImportId: string;
  row: AttendanceRowResponse;
}) {
  const { format, locale, t } = useI18n();
  const router = useRouter();
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<"idle" | "running" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (open) reasonRef.current?.focus();
  }, [open]);

  async function submit() {
    const normalizedReason = reason.trim();
    if (!normalizedReason) {
      setStatus(DELETE_STATUS.error);
      setMessage(t("Deletion reason is required."));
      reasonRef.current?.focus();
      return;
    }
    setStatus(DELETE_STATUS.running);
    setMessage(t("Deleting attendance row."));
    try {
      await deleteAttendanceRow(attendanceImportId, row.id, normalizedReason);
      setMessage(t("Attendance row deleted and history recorded."));
      setOpen(false);
      setReason("");
      setStatus(DELETE_STATUS.idle);
      router.refresh();
    } catch (error) {
      setStatus(DELETE_STATUS.error);
      setMessage(attendanceApiErrorMessage(error, locale));
    }
  }

  const employee = row.employeeName ?? t("Unknown employee");
  const punches = Array.isArray(row.punchTimes)
    ? row.punchTimes.map(String).join(", ")
    : t("Punch details unavailable");

  return (
    <>
      <button
        aria-label={format("i18n.workHours.deleteRowAria", {
          date: row.workDate,
          employee,
        })}
        className="min-h-9 border border-red-300 bg-white px-3 text-xs font-semibold text-red-800 hover:bg-red-50"
        onClick={() => {
          setMessage("");
          setStatus(DELETE_STATUS.idle);
          setOpen(true);
        }}
        type="button"
      >
        {t("Delete row")}
      </button>
      {open ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/60 p-4"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && status !== "running") setOpen(false);
          }}
        >
          <section
            aria-describedby="attendance-delete-description"
            aria-labelledby="attendance-delete-title"
            aria-modal="true"
            className="max-h-[90vh] w-full max-w-xl overflow-y-auto border border-zinc-300 bg-white p-5 shadow-2xl"
            role="dialog"
          >
            <h2 className="text-lg font-semibold text-zinc-950" id="attendance-delete-title">
              {t("Exclude attendance row from settlement?")}
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-600" id="attendance-delete-description">
              {t("The source row remains preserved. This action removes it from active totals and future wage records and writes an immutable deletion event.")}
            </p>
            <dl className="mt-4 grid gap-2 border border-zinc-200 bg-zinc-50 p-3 text-sm sm:grid-cols-2">
              <div><dt className="text-xs text-zinc-500">{t("Employee")}</dt><dd className="break-words font-medium">{employee} / {row.employeeId ?? t("No employee ID")}</dd></div>
              <div><dt className="text-xs text-zinc-500">{t("Date")}</dt><dd className="font-medium">{row.workDate}</dd></div>
              <div className="sm:col-span-2"><dt className="text-xs text-zinc-500">{t("Punches")}</dt><dd className="break-words font-medium">{punches}</dd></div>
              <div><dt className="text-xs text-zinc-500">{t("Hours")}</dt><dd className="font-medium">{formatHours(row.calculatedHours)}</dd></div>
              <div><dt className="text-xs text-zinc-500">{t("Department")}</dt><dd className="break-words font-medium">{row.department ?? t("Unknown department")}</dd></div>
            </dl>
            <label className="mt-4 block text-sm font-semibold text-zinc-950" htmlFor={`delete-reason-${row.id}`}>
              {t("Deletion reason")}
            </label>
            <textarea
              aria-invalid={status === "error" && !reason.trim()}
              className="mt-2 min-h-28 w-full resize-y border border-zinc-300 px-3 py-2 text-sm text-zinc-950"
              disabled={status === "running"}
              id={`delete-reason-${row.id}`}
              maxLength={500}
              onChange={(event) => {
                setReason(event.target.value);
                if (status === DELETE_STATUS.error) {
                  setMessage("");
                  setStatus(DELETE_STATUS.idle);
                }
              }}
              ref={reasonRef}
              value={reason}
            />
            <p aria-live="polite" className={`mt-2 min-h-5 text-sm ${status === "error" ? "text-red-800" : "text-zinc-600"}`} role={status === "error" ? "alert" : "status"}>
              {message}
            </p>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button className="min-h-10 border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950" disabled={status === "running"} onClick={() => setOpen(false)} type="button">
                {t("Cancel")}
              </button>
              <button className="min-h-10 border border-red-700 bg-red-700 px-4 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-300" disabled={status === "running"} onClick={() => void submit()} type="button">
                {status === "running" ? t("Deleting") : t("Delete row")}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
