/** Time out stalled loading, rather than a large download still making progress. */
export function createModelLoadWatchdog({
  onSlow,
  onIdle,
  slowMs = 15_000,
  idleMs = 120_000,
}: {
  onSlow: () => void;
  onIdle: () => void;
  slowMs?: number;
  idleMs?: number;
}) {
  let stopped = false;
  let progress = -1;
  let slow: ReturnType<typeof setTimeout>;
  let idle: ReturnType<typeof setTimeout>;
  const clear = () => {
    clearTimeout(slow);
    clearTimeout(idle);
  };
  const arm = () => {
    clear();
    slow = setTimeout(() => {
      if (!stopped) onSlow();
    }, slowMs);
    idle = setTimeout(() => {
      if (stopped) return;
      stopped = true;
      clear();
      onIdle();
    }, idleMs);
  };
  arm();
  return {
    progress(value: number) {
      if (
        stopped ||
        !Number.isFinite(value) ||
        value < 0 ||
        value > 1 ||
        value <= progress
      )
        return false;
      progress = value;
      arm();
      return true;
    },
    stop() {
      stopped = true;
      clear();
    },
  };
}
