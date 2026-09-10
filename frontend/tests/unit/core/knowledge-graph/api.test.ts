import { afterEach, expect, rs, test } from "@rstest/core";

afterEach(() => {
  rs.unstubAllGlobals();
});

test("queryGraph forwards cancellation to the graph request", async () => {
  const requests: Array<{ init?: RequestInit }> = [];
  rs.stubGlobal("fetch", async (_url: string, init?: RequestInit) => {
    requests.push({ init });
    return new Response(
      JSON.stringify({
        query: "木渎",
        status: "empty",
        message: "未找到",
        candidates: [],
        nodes: [],
        edges: [],
        evidence: [],
        truncated: false,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });

  const controller = new AbortController();
  const { queryGraph } = await import("@/core/knowledge-graph/api");
  await queryGraph("木渎", 3, { signal: controller.signal });

  expect(requests[0]?.init?.signal).toBe(controller.signal);
});
