import { afterEach, expect, rs, test } from "@rstest/core";

import {
  listQualityFeedback,
  reviewQualityFeedback,
  upsertFeedback,
} from "@/core/api/feedback";

afterEach(() => {
  rs.unstubAllGlobals();
});

function requestUrl(input: RequestInfo | URL) {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

test("submits categorized feedback and exposes the administrator queue", async () => {
  const fetchFn = rs.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    new Response(JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  rs.stubGlobal("fetch", fetchFn);

  await upsertFeedback("thread-1", "run-1", -1, "页码有误", "citation_error");
  await listQualityFeedback({ status: "submitted", page: 2, pageSize: 20 });

  expect(JSON.parse(fetchFn.mock.calls[0]![1]!.body as string)).toMatchObject({
    rating: -1,
    comment: "页码有误",
    category: "citation_error",
  });
  const queueUrl = new URL(requestUrl(fetchFn.mock.calls[1]![0]), "http://localhost");
  expect(queueUrl.pathname).toBe("/api/threads/feedback/quality-queue");
  expect(Object.fromEntries(queueUrl.searchParams)).toMatchObject({
    status: "submitted",
    limit: "20",
    offset: "20",
  });
});

test("persists an administrator review decision", async () => {
  const fetchFn = rs.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    new Response(JSON.stringify({ feedback_id: "f-1", status: "reviewing" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  rs.stubGlobal("fetch", fetchFn);

  await reviewQualityFeedback("f-1", "reviewing", "核对原文");

  expect(requestUrl(fetchFn.mock.calls[0]![0])).toContain(
    "/api/threads/feedback/f-1/review",
  );
  expect(JSON.parse(fetchFn.mock.calls[0]![1]!.body as string)).toEqual({
    status: "reviewing",
    review_note: "核对原文",
  });
});
