import { afterEach, expect, rs, test } from "@rstest/core";

import {
  fetchGraphCatalog,
  invalidateGraphCatalogCache,
  readCachedGraphCatalog,
  queryGraph,
  listAllEvents,
  reviewRelation,
  reviewEvent,
} from "@/core/knowledge-graph/api";

afterEach(() => {
  invalidateGraphCatalogCache();
  rs.unstubAllGlobals();
});

test("admin review catalog is explicit and never contaminates the ordinary cache", async () => {
  const requests: URL[] = [];
  rs.stubGlobal("fetch", async (url: string) => {
    const parsed = new URL(url, "http://localhost");
    requests.push(parsed);
    return new Response(
      JSON.stringify(
        parsed.searchParams.has("include_rejected")
          ? [{ id: "rejected", review_status: "rejected" }]
          : [],
      ),
    );
  });
  const publicCatalog = await fetchGraphCatalog();
  const adminCatalog = await fetchGraphCatalog({ includeRejected: true });
  expect(adminCatalog.relations[0]?.id).toBe("rejected");
  expect(readCachedGraphCatalog()).toBe(publicCatalog);
  expect((await fetchGraphCatalog()).relations).toEqual([]);
  expect(
    requests.filter(
      (url) => url.searchParams.get("include_rejected") === "true",
    ),
  ).toHaveLength(1);
  await listAllEvents({ includeRejected: true });
  expect(requests.at(-1)?.searchParams.get("include_rejected")).toBe("true");
});

test("review requests send all statuses, the note and the expected status, and return the server record", async () => {
  const requests: Array<{ url: string; body: unknown }> = [];
  rs.stubGlobal("fetch", async (url: string, init: RequestInit) => {
    if (typeof init.body !== "string")
      throw new Error("Expected JSON request body");
    const body = JSON.parse(init.body);
    requests.push({ url, body });
    return new Response(
      JSON.stringify({
        id: "server-record",
        review_status: body.review_status,
      }),
    );
  });
  for (const review of [reviewRelation, reviewEvent]) {
    for (const status of [
      "pending",
      "reviewed",
      "rejected",
      "disputed",
    ] as const) {
      const row = await review("record", status, "核对史料", "pending");
      expect(row.id).toBe("server-record");
      expect(row.review_status).toBe(status);
      expect(requests.at(-1)?.body).toEqual({
        review_status: status,
        review_note: "核对史料",
        expected_status: "pending",
      });
    }
  }
});

test("failed reviews preserve the explicit server error", async () => {
  rs.stubGlobal(
    "fetch",
    async () =>
      new Response(JSON.stringify({ detail: "审核状态已改变，请刷新" }), {
        status: 409,
      }),
  );
  await expect(
    reviewRelation("record", "pending", "重新核对", "reviewed"),
  ).rejects.toThrow("审核状态已改变，请刷新");
  await expect(
    reviewEvent("record", "disputed", "史料冲突", "reviewed"),
  ).rejects.toThrow("审核状态已改变，请刷新");
});

test("a query that started before a review cannot repopulate the invalidated cache", async () => {
  let finishOld!: (response: Response) => void;
  let calls = 0;
  const result = (message: string) =>
    new Response(
      JSON.stringify({ message, nodes: [], edges: [], evidence: [] }),
    );
  rs.stubGlobal("fetch", async () => {
    calls += 1;
    if (calls === 1)
      return new Promise<Response>((resolve) => {
        finishOld = resolve;
      });
    return result("已更新");
  });
  const oldRequest = queryGraph("record");
  invalidateGraphCatalogCache();
  expect((await queryGraph("record")).message).toBe("已更新");
  finishOld(result("旧结果"));
  await oldRequest;
  expect((await queryGraph("record")).message).toBe("已更新");
  expect(calls).toBe(2);
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

test("graph catalog follows entity and relation pages until both catalogs are complete", async () => {
  const requests: string[] = [];
  rs.stubGlobal("fetch", async (url: string) => {
    const parsed = new URL(url, "http://localhost");
    const offset = Number(parsed.searchParams.get("offset"));
    requests.push(`${parsed.pathname}:${offset}`);
    if (parsed.pathname.endsWith("/api/entities")) {
      const count = offset === 0 ? 1000 : offset === 1000 ? 1 : 0;
      return new Response(
        JSON.stringify(
          Array.from({ length: count }, (_, index) => ({
            id: `entity-${offset + index}`,
            canonical_name: `主体${offset + index}`,
            entity_type: "place",
            dynasty: null,
            extant_status: null,
            summary: null,
            review_status: "reviewed",
            release_id: null,
            evidence_ids: [],
          })),
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    const count = offset === 0 ? 2000 : offset === 2000 ? 1 : 0;
    return new Response(
      JSON.stringify(
        Array.from({ length: count }, (_, index) => ({
          id: `relation-${offset + index}`,
          subject_id: "entity-0",
          relation_type: "related_to",
          object_id: "entity-1",
          start_time: null,
          end_time: null,
          confidence: 1,
          evidence_ids: [],
          is_inferred: true,
          review_status: "pending",
          release_id: null,
        })),
      ),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });

  const catalog = await fetchGraphCatalog();

  expect(catalog.entities).toHaveLength(1001);
  expect(catalog.relations).toHaveLength(2001);
  expect(catalog.entities.at(-1)?.id).toBe("entity-1000");
  expect(catalog.relations.at(-1)?.id).toBe("relation-2000");
  expect([...requests].sort()).toEqual([
    "/api/entities:0",
    "/api/entities:1000",
    "/api/knowledge-graph/relations:0",
    "/api/knowledge-graph/relations:2000",
  ]);
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
