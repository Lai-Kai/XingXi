import { beforeEach, expect, rs, test } from "@rstest/core";

rs.mock("@/core/api/fetcher", () => ({ fetch: rs.fn() }));
rs.mock("@/core/config", () => ({ getBackendBaseURL: () => "/backend" }));

import { fetch as fetcher } from "@/core/api/fetcher";
import {
  createAgentCase,
  deleteAgentCase,
  evaluationVerdict,
  getAgentEvaluation,
  loadAgentCases,
  rerunAgentEvaluation,
  reviewAgentEvaluation,
  restoreAgentCase,
  startAgentEvaluation,
} from "@/core/operations/evaluations";

const mockedFetch = rs.mocked(fetcher);

beforeEach(() => {
  mockedFetch.mockReset();
});

test("question management uses persisted APIs and preserves selected question IDs", async () => {
  mockedFetch.mockImplementation(async () => new Response("{}"));
  const input = {
    title: "自定义问题",
    question: "测试桥位于哪里？",
    scenario: "grounded",
    mode: "pro" as const,
    expected_terms: ["测试溪"],
  };
  await loadAgentCases();
  await createAgentCase(input);
  await deleteAgentCase("custom/a");
  await restoreAgentCase("custom/a");
  await startAgentEvaluation(false, "single-question-key", ["custom/a"]);
  const calls = mockedFetch.mock.calls;
  expect(calls[0]?.[0]).toBe("/backend/api/operations/evaluations/cases");
  expect(calls[1]?.[1]?.method).toBe("POST");
  expect(calls[1]?.[1]?.body).toBe(JSON.stringify(input));
  expect(calls[2]?.[0]).toBe(
    "/backend/api/operations/evaluations/cases/custom%2Fa",
  );
  expect(calls[2]?.[1]?.method).toBe("DELETE");
  expect(calls[3]?.[0]).toBe(
    "/backend/api/operations/evaluations/cases/custom%2Fa/restore",
  );
  expect(calls[3]?.[1]?.method).toBe("POST");
  expect(calls[4]?.[1]?.body).toBe(
    JSON.stringify({
      smoke: false,
      request_key: "single-question-key",
      case_ids: ["custom/a"],
    }),
  );
});

test("question mutation failures expose the server error", async () => {
  mockedFetch.mockImplementation(
    async () => new Response('{"detail":"题目不可删除"}', { status: 403 }),
  );
  await expect(deleteAgentCase("one")).rejects.toThrow("题目不可删除");
  await expect(restoreAgentCase("one")).rejects.toThrow("题目不可删除");
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
