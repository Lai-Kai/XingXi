import { expect, test } from "@rstest/core";

import { createLatestRequestTracker } from "@/core/source-files/latest-request";

test("starting a request aborts and supersedes the previous request", () => {
  const tracker = createLatestRequestTracker();
  const first = tracker.start();
  const second = tracker.start();

  expect(first.signal.aborted).toBe(true);
  expect(tracker.isCurrent(first.sequence)).toBe(false);
  expect(tracker.isCurrent(second.sequence)).toBe(true);
});

test("cancelling a request aborts it and invalidates its sequence", () => {
  const tracker = createLatestRequestTracker();
  const request = tracker.start();

  tracker.cancel();

  expect(request.signal.aborted).toBe(true);
  expect(tracker.isCurrent(request.sequence)).toBe(false);
});
