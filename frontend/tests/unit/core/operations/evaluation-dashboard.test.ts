import { expect, test } from "@rstest/core";

import {
  evaluationDistribution,
  evaluationMetrics,
  filterObservations,
  historyPoints,
  orderedEvents,
} from "@/core/operations/evaluation-dashboard";

import { evaluationFixture } from "../../../fixtures/agent-evaluations";

test("missing and invalid durations stay unavailable and show their sample count", () => {
  const batch = evaluationFixture();
  batch.results.forEach((item) => {
    item.elapsed_ms = undefined;
  });
  batch.results[0]!.elapsed_ms = Number.NaN;
  batch.results[1]!.elapsed_ms = -1;
  expect(evaluationMetrics(batch).averageMs).toBeNull();
  expect(evaluationMetrics(batch).durationSamples).toBe(0);
  batch.results[0]!.elapsed_ms = 0;
  batch.results[1]!.elapsed_ms = 2000;
  expect(evaluationMetrics(batch).averageMs).toBe(1000);
  expect(evaluationMetrics(batch).durationSamples).toBe(2);
  expect(evaluationMetrics(undefined).passRate).toBeNull();
  expect(
    evaluationMetrics(
      evaluationFixture("empty", { results: [], total: 0, pass_rate: null }),
    ).errors,
  ).toBeNull();
});

test("unpassed distribution keeps verdict, execution errors and missing records distinct", () => {
  const batch = evaluationFixture();
  expect(
    evaluationDistribution(batch).map(({ key, value }) => [key, value]),
  ).toEqual([
    ["failed", 1],
    ["error", 1],
    ["needs_review", 1],
  ]);
  batch.total += 2;
  expect(
    evaluationDistribution(batch).find((item) => item.key === "missing")?.value,
  ).toBe(2);
  expect(evaluationDistribution(undefined)).toEqual([]);
});

test("expected timeout cancellation remains a pass and filters combine query, mode and verdict", () => {
  const batch = evaluationFixture();
  expect(
    filterObservations(batch.results, {
      scenario: "timeout",
      mode: "pro",
      outcome: "passed",
      query: "中断",
    }),
  ).toHaveLength(1);
  expect(
    filterObservations(batch.results, {
      scenario: "timeout",
      mode: "flash",
      outcome: "all",
      query: "",
    }),
  ).toEqual([]);
  expect(
    filterObservations(batch.results, {
      scenario: "all",
      mode: "all",
      outcome: "unpassed",
      query: "",
    }),
  ).toHaveLength(3);
});

test("timeline follows persisted sequence without changing the response", () => {
  const events = evaluationFixture().results[0]!.events;
  expect(orderedEvents(events).map((item) => item.seq)).toEqual([1, 2, 3]);
  expect(events.map((item) => item.seq)).toEqual([3, 1, 2]);
});

test("history never plots an unfinished batch as a finished 100 percent pass", () => {
  const complete = evaluationFixture("complete", { pass_rate: 0.7 });
  const running = evaluationFixture("running", {
    status: "running",
    passed: 10,
    pass_rate: 1,
  });
  const points = historyPoints([running, complete]);
  expect(points.find((item) => item.id === "complete")?.rate).toBe(70);
  expect(points.find((item) => item.id === "running")?.rate).toBeNull();
});
