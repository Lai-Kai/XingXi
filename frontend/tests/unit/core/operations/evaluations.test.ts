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

const catalogCase = {
  id: "grounded-pro",
  version: 1,
  title: "服务端桥梁测试",
  question: "测试桥在哪里？",
  mode: "pro",
  scenario: "grounded",
  review_rubric: "核对检索工具与有效引用。",
  required_tool: "search_sources",
  min_citations: 1,
};

beforeEach(() => {
  mockedFetch.mockReset();
});

test("question management uses persisted APIs and preserves selected question IDs", async () => {
  mockedFetch.mockImplementation(async () => new Response("{}"));
  mockedFetch.mockResolvedValueOnce(
    new Response(
      JSON.stringify({ execution_mode: "replay", cases: [], methods: [] }),
    ),
  );
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
  expect(calls[0]?.[0]).toBe("/backend/api/operations/evaluations/questions");
  expect(calls[1]?.[0]).toBe("/backend/api/operations/evaluations/questions");
  expect(calls[1]?.[1]?.method).toBe("POST");
  expect(calls[1]?.[1]?.body).toBe(JSON.stringify(input));
  expect(calls[2]?.[0]).toBe(
    "/backend/api/operations/evaluations/questions/custom%2Fa",
  );
  expect(calls[2]?.[1]?.method).toBe("DELETE");
  expect(calls[3]?.[0]).toBe(
    "/backend/api/operations/evaluations/questions/custom%2Fa/restore",
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

test("the manual question array is rejected before rendering the method panel", async () => {
  for (const data of [
    [],
    null,
    {},
    { cases: [] },
    { cases: [], methods: null },
  ]) {
    mockedFetch.mockResolvedValueOnce(new Response(JSON.stringify(data)));
    await expect(loadAgentCases()).rejects.toThrow(
      "暂时无法读取测试问题与方法，请重试。",
    );
  }
});

test("a valid question collection retains complete questions and methods", async () => {
  const collection = {
    execution_mode: "replay",
    cases: [{ id: "grounded-pro", question: "测试桥在哪里？", active: true }],
    methods: [{ scenario: "grounded", description: "核对工具和有效引用" }],
  };
  mockedFetch.mockResolvedValueOnce(new Response(JSON.stringify(collection)));
  expect(await loadAgentCases()).toEqual(collection);
});

test("a missing management route reads actual catalog questions and rules in read-only mode", async () => {
  mockedFetch.mockResolvedValueOnce(
    new Response('{"detail":"Not Found"}', { status: 404 }),
  );
  mockedFetch.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        version: "old-service",
        execution_mode: "replay",
        available: true,
        cases: [catalogCase],
      }),
    ),
  );
  const result = await loadAgentCases();
  expect(result).toEqual({
    execution_mode: "replay",
    management_available: false,
    methods: [],
    cases: [{ ...catalogCase, active: true, builtin: null }],
  });
  expect(mockedFetch.mock.calls.map(([path]) => path)).toEqual([
    "/backend/api/operations/evaluations/questions",
    "/backend/api/operations/evaluations/catalog",
  ]);
});

test("both missing routes explain service availability instead of displaying raw Not Found", async () => {
  mockedFetch.mockImplementation(
    async () => new Response('{"detail":"Not Found"}', { status: 404 }),
  );
  await expect(loadAgentCases()).rejects.toThrow(
    "评测题库暂不可用，请更新并重启评测服务后重试。",
  );
});

test("catalog compatibility rejects invalid questions and never uses the manual cases API", async () => {
  for (const catalog of [
    [],
    {},
    { execution_mode: "replay", cases: [{}] },
    { execution_mode: "live", cases: [catalogCase] },
  ]) {
    mockedFetch.mockResolvedValueOnce(
      new Response('{"detail":"Not Found"}', { status: 404 }),
    );
    mockedFetch.mockResolvedValueOnce(new Response(JSON.stringify(catalog)));
    await expect(loadAgentCases()).rejects.toThrow(
      "暂时无法读取测试问题与方法，请重试。",
    );
  }
  expect(
    mockedFetch.mock.calls.some(
      ([path]) => typeof path === "string" && path.endsWith("/cases"),
    ),
  ).toBe(false);
});

test("permission, server and cancellation failures do not trigger catalog compatibility", async () => {
  for (const status of [401, 403, 503]) {
    mockedFetch.mockReset();
    mockedFetch.mockResolvedValueOnce(
      new Response('{"detail":"读取被拒绝"}', { status }),
    );
    await expect(loadAgentCases()).rejects.toThrow("读取被拒绝");
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  }
  mockedFetch.mockReset();
  mockedFetch.mockRejectedValueOnce(
    new DOMException("Request cancelled", "AbortError"),
  );
  await expect(loadAgentCases()).rejects.toThrow("Request cancelled");
  expect(mockedFetch).toHaveBeenCalledTimes(1);
});

test("compatibility preserves abort signals and returns to full management after a service update", async () => {
  const controller = new AbortController();
  mockedFetch.mockResolvedValueOnce(
    new Response('{"detail":"Not Found"}', { status: 404 }),
  );
  mockedFetch.mockResolvedValueOnce(
    new Response(JSON.stringify({ execution_mode: "replay", cases: [] })),
  );
  await loadAgentCases(controller.signal);
  expect(mockedFetch.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
  expect(mockedFetch.mock.calls[1]?.[1]?.signal).toBe(controller.signal);
  const current = { execution_mode: "replay", cases: [], methods: [] };
  mockedFetch.mockResolvedValueOnce(new Response(JSON.stringify(current)));
  expect(await loadAgentCases()).toEqual(current);
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
