import { beforeEach, expect, rs, test } from "@rstest/core";

rs.mock("@/core/api/fetcher", () => ({ fetch: rs.fn() }));
rs.mock("@/core/config", () => ({ getBackendBaseURL: () => "/backend" }));

import { fetch as fetcher } from "@/core/api/fetcher";
import {
  evaluationVerdict,
  getAgentEvaluation,
  rerunAgentEvaluation,
  reviewAgentEvaluation,
  startAgentEvaluation,
} from "@/core/operations/evaluations";

const mockedFetch = rs.mocked(fetcher);

beforeEach(() => {
  mockedFetch.mockReset();
});

test("incomplete and empty batches cannot display all passed", () => {
  expect(evaluationVerdict({ status: "running", total: 6, passed: 6 })).toBe(
    "执行中",
  );
  expect(evaluationVerdict({ status: "error", total: 6, passed: 6 })).toBe(
    "执行错误",
  );
  expect(evaluationVerdict({ status: "cancelled", total: 6, passed: 1 })).toBe(
    "已取消",
  );
  expect(evaluationVerdict({ status: "completed", total: 0, passed: 0 })).toBe(
    "未全部通过",
  );
  expect(evaluationVerdict({ status: "completed", total: 6, passed: 6 })).toBe(
    "全部通过",
  );
});

test("start and rerun send an idempotency key and keep rerun linked to its parent", async () => {
  mockedFetch.mockImplementation(
    async () => new Response('{"id":"new-batch"}'),
  );
  await startAgentEvaluation(true, "stable-request-key");
  await rerunAgentEvaluation("original", "rerun-request-key");
  expect(mockedFetch.mock.calls[0]?.[1]?.body).toBe(
    JSON.stringify({ smoke: true, request_key: "stable-request-key" }),
  );
  expect(mockedFetch.mock.calls[1]?.[0]).toBe(
    "/backend/api/operations/evaluations/executions/original/rerun",
  );
  expect(mockedFetch.mock.calls[1]?.[1]?.body).toBe(
    JSON.stringify({ request_key: "rerun-request-key", failed_only: true }),
  );
});

test("read failures and review failures remain visible", async () => {
  mockedFetch.mockImplementation(
    async () =>
      new Response('{"detail":"Governance privileges are required"}', {
        status: 403,
      }),
  );
  await expect(getAgentEvaluation("restricted")).rejects.toThrow();
  await expect(
    reviewAgentEvaluation("restricted", {
      case_id: "one",
      decision: "confirmed",
      note: "复核",
    }),
  ).rejects.toThrow();
});
