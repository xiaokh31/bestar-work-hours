"use client";

import { useEffect, useState } from "react";
import { useI18n } from "../i18n/i18n-provider";
import { formatOperationalDateTime } from "../../lib/date-time";
import {
  OPERATIONAL_CLOCK_BREAKPOINT,
  startOperationalClockScheduler,
  type OperationalClockEnvironment,
} from "../../lib/operational-clock-scheduler";

export function OperationalClock({ initialIso }: { initialIso: string }) {
  // The clock has no UI copy of its own, but remains inside the explicit locale
  // boundary so a future in-place locale change cannot bypass the i18n contract.
  const { t } = useI18n();
  const [clock, setClock] = useState(() => ({
    epochMs: new Date(initialIso).getTime(),
    renderCount: 0,
  }));
  const [running, setRunning] = useState(false);
  const [drifted, setDrifted] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia(OPERATIONAL_CLOCK_BREAKPOINT);
    const environment: OperationalClockEnvironment<number> = {
      cancelTimer: (handle) => window.clearTimeout(handle),
      isDocumentVisible: () => document.visibilityState === "visible",
      isViewportVisible: () => mediaQuery.matches,
      monotonicNow: () => performance.now(),
      requestServerTime: async (signal) => {
        const response = await fetch("/api/health", {
          cache: "no-store",
          signal,
        });
        if (!response.ok) {
          throw new Error("clock sync failed");
        }
        const body = (await response.json()) as { serverTime?: string };
        const epochMs = Date.parse(body.serverTime ?? "");
        if (!Number.isFinite(epochMs)) {
          throw new Error("clock sync response invalid");
        }
        return epochMs;
      },
      scheduleTimer: (callback, delayMs) =>
        window.setTimeout(callback, delayMs),
      subscribeDocumentVisibility: (callback) => {
        document.addEventListener("visibilitychange", callback);
        return () => document.removeEventListener("visibilitychange", callback);
      },
      subscribeViewportVisibility: (callback) => {
        mediaQuery.addEventListener("change", callback);
        return () => mediaQuery.removeEventListener("change", callback);
      },
      wallNow: () => Date.now(),
    };

    return startOperationalClockScheduler({
      environment,
      initialServerEpochMs: new Date(initialIso).getTime(),
      onDriftChange: setDrifted,
      onRunningChange: setRunning,
      onTick: (epochMs) =>
        setClock((current) => ({
          epochMs,
          renderCount: current.renderCount + 1,
        })),
    });
  }, [initialIso]);

  const date = new Date(clock.epochMs);
  const isoValue = date.toISOString();

  return (
    <>
      <time
        className="font-data mt-1 block"
        data-clock-drifted={drifted}
        data-clock-render-count={clock.renderCount}
        data-clock-running={running}
        data-operational-clock="true"
        dateTime={isoValue}
      >
        {formatOperationalDateTime(date)}
      </time>
      {drifted ? (
        <span
          className="mt-1 block max-w-44 text-[10px] font-semibold text-amber-200"
          data-clock-drift-warning="true"
          role="status"
        >
          {t("Device time is out of sync")}
        </span>
      ) : null}
    </>
  );
}
