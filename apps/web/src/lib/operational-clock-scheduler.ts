export const OPERATIONAL_CLOCK_BREAKPOINT = "(min-width: 1280px)";
export const DEVICE_CLOCK_DRIFT_THRESHOLD_MS = 5 * 60 * 1000;

export interface OperationalClockEnvironment<TimerHandle = unknown> {
  cancelTimer: (handle: TimerHandle) => void;
  isDocumentVisible: () => boolean;
  isViewportVisible: () => boolean;
  monotonicNow: () => number;
  requestServerTime?: (signal: AbortSignal) => Promise<number>;
  scheduleTimer: (callback: () => void, delayMs: number) => TimerHandle;
  subscribeDocumentVisibility: (callback: () => void) => () => void;
  subscribeViewportVisibility: (callback: () => void) => () => void;
  wallNow: () => number;
}

export interface OperationalClockSchedulerOptions<TimerHandle = unknown> {
  environment: OperationalClockEnvironment<TimerHandle>;
  initialServerEpochMs: number;
  onDriftChange?: (drifted: boolean) => void;
  onRunningChange?: (running: boolean) => void;
  onTick: (epochMs: number) => void;
}

/**
 * Advances a server-provided epoch with monotonic elapsed time. The client wall
 * clock is diagnostic only and a bounded server resync runs after visibility
 * or breakpoint resume.
 */
export function startOperationalClockScheduler<TimerHandle>({
  environment,
  initialServerEpochMs,
  onDriftChange,
  onRunningChange,
  onTick,
}: OperationalClockSchedulerOptions<TimerHandle>): () => void {
  let disposed = false;
  let running = false;
  let drifted = false;
  let timer: TimerHandle | null = null;
  let syncController: AbortController | null = null;
  let baselineEpochMs = initialServerEpochMs;
  let baselineMonotonicMs = environment.monotonicNow();

  const authoritativeNow = () =>
    baselineEpochMs +
    Math.max(0, environment.monotonicNow() - baselineMonotonicMs);

  const stopTimer = () => {
    if (timer !== null) {
      environment.cancelTimer(timer);
      timer = null;
    }
  };

  const setRunning = (nextRunning: boolean) => {
    if (running !== nextRunning) {
      running = nextRunning;
      onRunningChange?.(running);
    }
  };

  const emitTick = () => {
    const epochMs = authoritativeNow();
    onTick(epochMs);
    const nextDrifted =
      Math.abs(environment.wallNow() - epochMs) >
      DEVICE_CLOCK_DRIFT_THRESHOLD_MS;
    if (nextDrifted !== drifted) {
      drifted = nextDrifted;
      onDriftChange?.(drifted);
    }
    return epochMs;
  };

  const shouldRun = () =>
    environment.isDocumentVisible() && environment.isViewportVisible();

  const scheduleNextTick = (epochMs: number) => {
    const remainder = ((epochMs % 1000) + 1000) % 1000;
    const delayMs = remainder === 0 ? 1000 : 1000 - remainder;
    timer = environment.scheduleTimer(runTick, delayMs);
  };

  const runTick = () => {
    timer = null;
    if (disposed || !shouldRun()) {
      setRunning(false);
      return;
    }
    scheduleNextTick(emitTick());
  };

  const requestResync = () => {
    if (!environment.requestServerTime || syncController) {
      return;
    }
    const controller = new AbortController();
    syncController = controller;
    const requestedAt = environment.monotonicNow();
    void environment
      .requestServerTime(controller.signal)
      .then((serverEpochMs) => {
        if (disposed || controller.signal.aborted || !Number.isFinite(serverEpochMs)) {
          return;
        }
        const receivedAt = environment.monotonicNow();
        baselineEpochMs =
          serverEpochMs + Math.max(0, receivedAt - requestedAt) / 2;
        baselineMonotonicMs = receivedAt;
        if (shouldRun()) {
          stopTimer();
          scheduleNextTick(emitTick());
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (syncController === controller) {
          syncController = null;
        }
      });
  };

  const reconcile = (resyncAfterResume: boolean) => {
    const wasRunning = running;
    stopTimer();
    if (disposed || !shouldRun()) {
      setRunning(false);
      return;
    }

    setRunning(true);
    scheduleNextTick(emitTick());
    if (resyncAfterResume && !wasRunning) {
      requestResync();
    }
  };

  const unsubscribeDocument =
    environment.subscribeDocumentVisibility(() => reconcile(true));
  const unsubscribeViewport =
    environment.subscribeViewportVisibility(() => reconcile(true));
  reconcile(false);

  return () => {
    if (disposed) {
      return;
    }
    disposed = true;
    stopTimer();
    syncController?.abort();
    syncController = null;
    running = false;
    unsubscribeDocument();
    unsubscribeViewport();
  };
}
