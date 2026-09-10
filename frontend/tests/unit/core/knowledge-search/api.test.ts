import { afterEach, expect, test, rs } from "@rstest/core";

afterEach(() => {
  rs.unstubAllGlobals();
});

test("structured search sends the shared nested filter schema and cursor", async () => {
  const requests: Array<{ url: string; init?: RequestInit }> = [];
  rs.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    requests.push({ url, init });
    return new Response(
      JSON.stringify({
        query: "旧桥",
        release_id: "release-1",
        filters: { dynasties: ["qing"], entity_types: ["bridge"] },
        page_size: 20,
        returned_count: 0,
        candidate_count: 0,
        has_more: false,
        next_cursor: null,
        degraded: false,
        evidence_status: "insufficient",
        message: "暂无明确方志记载",
        hits: [],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });

  const { searchStructuredKnowledge } =
    await import("@/core/knowledge-search/api");
  const result = await searchStructuredKnowledge({
    query: "旧桥",
    filters: { dynasties: ["qing"], entity_types: ["bridge"] },
    cursor: "cursor-1",
  });

  expect(requests[0]?.url).toBe("/api/knowledge-search/structured");
  expect(JSON.parse(requests[0]?.init?.body as string)).toEqual({
    query: "旧桥",
    filters: { dynasties: ["qing"], entity_types: ["bridge"] },
    cursor: "cursor-1",
  });
  expect(result.release_id).toBe("release-1");
});

test("structured search surfaces the gateway cursor error", async () => {
  rs.stubGlobal(
    "fetch",
    async () =>
      new Response(
        JSON.stringify({
          detail: {
            code: "invalid_search_cursor",
            message: "cursor belongs to a different query or filter set",
          },
        }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      ),
  );
  const { searchStructuredKnowledge } =
    await import("@/core/knowledge-search/api");

  await expect(
    searchStructuredKnowledge({ query: "旧桥", cursor: "stale" }),
  ).rejects.toThrow("cursor belongs to a different query or filter set");
});
