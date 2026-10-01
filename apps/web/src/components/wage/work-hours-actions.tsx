"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/components/i18n/i18n-provider";
import {
  type AttendanceImportResponse,
  parseAttendanceImport,
  generateAttendanceWageRecord,
  uploadAttendanceImportFile,
} from "@/lib/api-client";
import {
  attendanceApiErrorMessage,
  attendanceUploadError,
  canGenerateWageRecord,
  wageGenerationBlockReason,
} from "./attendance-flow";

interface ActionState {
  message: string;
  status: "error" | "idle" | "running" | "success";
}

const idleState: ActionState = { message: "", status: "idle" };

export function AttendanceUploadPanel() {
  const { format, locale, t } = useI18n();
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<ActionState>(idleState);
  useEffect(() => setState(idleState), [locale]);

  async function upload() {
    const validationError = attendanceUploadError(file, locale);
    if (validationError || !file) {
      setState({
        message:
          validationError ?? t("Select one legacy .xls attendance workbook."),
        status: "error",
      });
      return;
    }

    setState({ message: t("Uploading attendance workbook."), status: "running" });
    try {
      const result = await uploadAttendanceImportFile(file);
      setState({
        message: format("i18n.workHours.uploadedFilename", {
          filename: result.originalFilename,
        }),
        status: "success",
      });
      if (inputRef.current) {
        inputRef.current.value = "";
      }
      setFile(null);
      router.push(
        `/?attendanceImportId=${encodeURIComponent(result.id)}`,
      );
      router.refresh();
    } catch (error) {
      setState({
        message: attendanceApiErrorMessage(error, locale),
        status: "error",
      });
    }
  }

  return (
    <section className="border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="grid gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div>
          <h2 className="text-base font-semibold text-zinc-950">
            {t("Upload attendance workbook")}
          </h2>
          <p className="mt-2 text-sm leading-6 text-zinc-600">
            {t(
              "Use the monthly time-clock .xls export. The API stores the original file and rejects duplicate SHA-256 content.",
            )}
          </p>
        </div>
        <div className="grid gap-3">


            <>
              <input
                accept=".xls,application/vnd.ms-excel"
                aria-label={t("Choose attendance file")}
                className="sr-only"
                disabled={state.status === "running"}
                id="attendance-workbook-file"
                onChange={(event) => {
                  const selectedFile = event.target.files?.[0] ?? null;
                  setFile(selectedFile);
                  const validationError = attendanceUploadError(
                    selectedFile,
                    locale,
                  );
                  setState(
                    validationError
                      ? { message: validationError, status: "error" }
                      : idleState,
                  );
                }}
                ref={inputRef}
                type="file"
              />
              <div className="flex min-h-10 min-w-0 flex-wrap items-center gap-3 border border-zinc-300 bg-white p-2 text-sm text-zinc-950">
                <button
                  className="min-h-9 shrink-0 border border-zinc-300 bg-zinc-100 px-3 font-semibold hover:bg-zinc-200"
                  disabled={state.status === "running"}
                  onClick={() => inputRef.current?.click()}
                  type="button"
                >
                  {t("Choose attendance file")}
                </button>
                <span className="min-w-0 break-all">
                  {file?.name ?? t("No attendance file selected")}
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  className="min-h-10 border border-teal-700 bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-200 disabled:text-zinc-500"
                  disabled={state.status === "running"}
                  onClick={() => void upload()}
                  type="button"
                >
                  {state.status === "running" ? t("Uploading") : t("Upload .xls")}
                </button>
                <button
                  className="min-h-10 border border-zinc-300 bg-white px-4 text-sm font-semibold text-zinc-950 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:text-zinc-400"
                  disabled={state.status === "running" || !file}
                  onClick={() => {
                    setFile(null);
                    setState(idleState);
                    if (inputRef.current) {
                      inputRef.current.value = "";
                    }
                  }}
                  type="button"
                >
                  {t("Clear")}
                </button>
              </div>
            </>

          <ActionMessage state={state} />
        </div>
      </div>
    </section>
  );
}

export function AttendanceImportActions({
  attendanceImport,
}: {
  attendanceImport: AttendanceImportResponse;
}) {
  const { format, locale, t } = useI18n();
  const router = useRouter();
  const [state, setState] = useState<ActionState>(idleState);
  useEffect(() => setState(idleState), [locale]);
  const [generationFailed, setGenerationFailed] = useState(false);
  const isReadyToGenerate = canGenerateWageRecord(attendanceImport);
  const generateBlockReason = wageGenerationBlockReason(attendanceImport, locale);

  async function runParse() {
    setGenerationFailed(false);

    setState({ message: t("Parsing attendance workbook."), status: "running" });
    try {
      const result = await parseAttendanceImport(attendanceImport.id);
      setState({
        message: format("i18n.workHours.parsedRows", {
          count: result.rows.length,
        }),
        status: "success",
      });
      router.refresh();
    } catch (error) {
      setState({
        message: attendanceApiErrorMessage(error, locale),
        status: "error",
      });
    }
  }

  async function generate() {

    if (!isReadyToGenerate) {
      setState({
        message:
          generateBlockReason ??
          t("This attendance import cannot generate a wage record yet."),
        status: "error",
      });
      return;
    }

    setState({
      message: t("Generating wage record workbook."),
      status: "running",
    });
    setGenerationFailed(false);
    try {
      await generateAttendanceWageRecord(attendanceImport.id);
      setState({
        message: t("Wage record generated. File history refreshed."),
        status: "success",
      });
      setGenerationFailed(false);
      router.refresh();
    } catch (error) {
      setGenerationFailed(true);
      setState({
        message: attendanceApiErrorMessage(error, locale),
        status: "error",
      });
    }
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-2">

          <button
            className="min-h-10 border border-teal-700 bg-white px-4 text-sm font-semibold text-teal-900 hover:bg-teal-50 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:text-zinc-400"
            disabled={state.status === "running"}
            onClick={() => void runParse()}
            type="button"
          >
            {t("Parse")}
          </button>


          <button
            className="min-h-10 border border-teal-700 bg-teal-700 px-4 text-sm font-semibold text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:border-zinc-300 disabled:bg-zinc-200 disabled:text-zinc-500"
            disabled={state.status === "running" || !isReadyToGenerate}
            onClick={() => void generate()}
            type="button"
            title={generateBlockReason ?? t("Generate wage record workbook")}
          >
            {generationFailed
              ? t("Retry wage record generation")
              : t("Generate wage record")}
          </button>

      </div>

      {generateBlockReason ? (
        <p className="text-xs font-medium text-amber-800">
          {generateBlockReason}
        </p>
      ) : null}
      <ActionMessage state={state} />
    </div>
  );
}

function ActionMessage({ state }: { state: ActionState }) {
  if (!state.message) {
    return null;
  }

  const styles =
    state.status === "error"
      ? "border-red-200 bg-red-50 text-red-900"
      : state.status === "success"
        ? "border-emerald-200 bg-emerald-50 text-emerald-900"
        : "border-zinc-200 bg-zinc-50 text-zinc-700";

  return (
    <p className={`border px-3 py-2 text-sm ${styles}`} role="status">
      {state.message}
    </p>
  );
}
