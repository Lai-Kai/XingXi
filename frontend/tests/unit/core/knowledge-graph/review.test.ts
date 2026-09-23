import { expect, test } from "@rstest/core";

import {
  matchesReviewFilter,
  reviewActions,
  reviewNoteRequired,
} from "@/core/knowledge-graph/review";
import type { ReviewStatus } from "@/core/knowledge-graph/types";

const statuses: ReviewStatus[] = [
  "pending",
  "reviewed",
  "disputed",
  "rejected",
];

test("every status can transition to the other three statuses", () => {
  for (const current of statuses) {
    expect(
      reviewActions(current)
        .map((action) => action.status)
        .sort(),
    ).toEqual(statuses.filter((status) => status !== current).sort());
  }
});

test("rejections, disputes and corrections require a note", () => {
  for (const current of statuses) {
    for (const action of reviewActions(current)) {
      expect(reviewNoteRequired(current, action.status)).toBe(
        current !== "pending" || action.status !== "reviewed",
      );
    }
  }
});

test("rejected records require the explicit administrator filter", () => {
  for (const filter of ["all", "reviewed", "draft"] as const) {
    expect(matchesReviewFilter("rejected", filter, true)).toBe(false);
  }
  expect(matchesReviewFilter("rejected", "rejected", false)).toBe(false);
  expect(matchesReviewFilter("rejected", "rejected", true)).toBe(true);
  expect(matchesReviewFilter("pending", "draft", false)).toBe(true);
  expect(matchesReviewFilter("disputed", "draft", false)).toBe(true);
  expect(matchesReviewFilter("reviewed", "draft", true)).toBe(false);
});
