import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";

import { createModelLoadWatchdog } from "@/core/map/model-load-watchdog";

beforeEach(() => {
  rs.useFakeTimers();
});
afterEach(() => {
  rs.useRealTimers();
});

describe("building model loading watchdog", () => {
  it("allows an active download to exceed the old two-minute total deadline", async () => {
    const idle = rs.fn();
    const watch = createModelLoadWatchdog({
      onIdle: idle,
      onSlow: () => undefined,
    });
    for (const value of [0.1, 0.2, 0.3]) {
      await rs.advanceTimersByTimeAsync(100_000);
      expect(watch.progress(value)).toBe(true);
    }
    expect(idle).not.toHaveBeenCalled();
    await rs.advanceTimersByTimeAsync(120_000);
    expect(idle).toHaveBeenCalledTimes(1);
  });

  it("repeated, regressive and invalid progress cannot hide a stalled transfer", async () => {
    const idle = rs.fn();
    const watch = createModelLoadWatchdog({
      onIdle: idle,
      onSlow: () => undefined,
    });
    watch.progress(0.5);
    await rs.advanceTimersByTimeAsync(100_000);
    for (const value of [0.5, 0.2, NaN, Infinity, -0.1, 1.1])
      expect(watch.progress(value)).toBe(false);
    await rs.advanceTimersByTimeAsync(20_000);
    expect(idle).toHaveBeenCalledTimes(1);
    expect(watch.progress(0.9)).toBe(false);
  });

  it("warns about slow loading without declaring failure", async () => {
    const slow = rs.fn(),
      idle = rs.fn();
    const watch = createModelLoadWatchdog({ onIdle: idle, onSlow: slow });
    await rs.advanceTimersByTimeAsync(15_000);
    expect(slow).toHaveBeenCalledTimes(1);
    expect(idle).not.toHaveBeenCalled();
    expect(watch.progress(0.01)).toBe(true);
    await rs.advanceTimersByTimeAsync(15_000);
    expect(slow).toHaveBeenCalledTimes(2);
    watch.stop();
  });

  it("clears pending feedback after success or unmount", async () => {
    const slow = rs.fn(),
      idle = rs.fn();
    const watch = createModelLoadWatchdog({ onIdle: idle, onSlow: slow });
    watch.stop();
    await rs.advanceTimersByTimeAsync(300_000);
    expect(slow).not.toHaveBeenCalled();
    expect(idle).not.toHaveBeenCalled();
    expect(watch.progress(1)).toBe(false);
  });
});
