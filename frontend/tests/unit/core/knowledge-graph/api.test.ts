import { afterEach, expect, rs, test } from "@rstest/core";

import {
  fetchGraphCatalog,
  invalidateGraphCatalogCache,
  readCachedGraphCatalog,
  queryGraph,
} from "@/core/knowledge-graph/api";

afterEach(() => {
  invalidateGraphCatalogCache();
  rs.unstubAllGlobals();
});

test("graph catalog reuses the latest successful session response", async () => {
  const requests: string[] = [];
  rs.stubGlobal("fetch", async (url: string) => {
    requests.push(url);
    const body = url.includes("/api/entities")
      ? [
          {
            id: "place-mudu",
            canonical_name: "木渎",
            entity_type: "place",
            dynasty: null,
            extant_status: null,
            summary: null,
            review_status: "reviewed",
            release_id: "release-1",
            evidence_ids: ["evidence-1"],
          },
        ]
      : [];
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  const first = await fetchGraphCatalog();
  const second = await fetchGraphCatalog();

  expect(first.entities[0]?.canonical_name).toBe("木渎");
  expect(second).toBe(first);
  expect(readCachedGraphCatalog()).toBe(first);
  expect(requests).toHaveLength(2);
});

test("graph catalog shares an in-flight load", async () => {
  const requests: string[] = [];
  rs.stubGlobal("fetch", async (url: string) => {
    requests.push(url);
    await new Promise((resolve) => setTimeout(resolve, 10));
    return new Response(JSON.stringify([]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  const [first, second] = await Promise.all([
    fetchGraphCatalog(),
    fetchGraphCatalog(),
  ]);

  expect(first).toBe(second);
  expect(requests).toHaveLength(2);
});

test("graph depth changes stay in the requested Release and use separate cache entries", async () => {
  const requests: URL[] = [];
  rs.stubGlobal("fetch", async (url: string) => {
    const parsed = new URL(url, "http://localhost");
    requests.push(parsed);
    return new Response(
      JSON.stringify({
        query: "person-1",
        status: "supported",
        message: "",
        candidates: [],
        nodes: [],
        edges: [],
        evidence: [],
        truncated: false,
        release_id: parsed.searchParams.get("release_id"),
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });
  await queryGraph("person-1", 2, { releaseId: "release-1" });
  await queryGraph("person-1", 3, { releaseId: "release-1" });
  await queryGraph("person-1", 3, { releaseId: "release-2" });
  await queryGraph("person-1", 3, { releaseId: "release-2" });
  expect(
    requests.map((url) => [
      url.searchParams.get("max_depth"),
      url.searchParams.get("release_id"),
    ]),
  ).toEqual([
    ["2", "release-1"],
    ["3", "release-1"],
    ["3", "release-2"],
  ]);
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
