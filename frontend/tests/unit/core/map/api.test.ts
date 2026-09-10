import { afterEach, expect, rs, test } from "@rstest/core";

import {
  fetchMapCatalog,
  invalidateMapCatalogCache,
  readCachedMapCatalog,
} from "@/core/map/api";

afterEach(() => {
  invalidateMapCatalogCache();
  rs.unstubAllGlobals();
});

test("map catalog reuses the latest successful session response", async () => {
  const requests: string[] = [];
  rs.stubGlobal("fetch", async (url: string) => {
    requests.push(url);
    return new Response(
      JSON.stringify({
        updated_at: "2026-09-07",
        data_notice: "active release",
        points: [],
        layers: [],
        events: [],
        relations: [],
        trajectories: [],
        routes: [],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });

  const first = await fetchMapCatalog();
  const second = await fetchMapCatalog();

  expect(first.updatedAt).toBe("2026-09-07");
  expect(second).toBe(first);
  expect(readCachedMapCatalog()).toBe(first);
  expect(requests).toHaveLength(1);
});

test("map catalog shares an in-flight load", async () => {
  let requestCount = 0;
  rs.stubGlobal("fetch", async () => {
    requestCount += 1;
    await new Promise((resolve) => setTimeout(resolve, 10));
    return new Response(
      JSON.stringify({
        updated_at: "2026-09-07",
        data_notice: "active release",
        points: [],
        layers: [],
        events: [],
        relations: [],
        trajectories: [],
        routes: [],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });

  const [first, second] = await Promise.all([
    fetchMapCatalog(),
    fetchMapCatalog(),
  ]);

  expect(first).toBe(second);
  expect(requestCount).toBe(1);
});

test("forced map refresh bypasses and replaces the session cache", async () => {
  let requestCount = 0;
  rs.stubGlobal("fetch", async () => {
    requestCount += 1;
    return new Response(
      JSON.stringify({
        updated_at: `2026-09-0${requestCount}`,
        data_notice: "active release",
        points: [],
        layers: [],
        events: [],
        relations: [],
        trajectories: [],
        routes: [],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });

  await fetchMapCatalog();
  const refreshed = await fetchMapCatalog(undefined, { force: true });

  expect(refreshed.updatedAt).toBe("2026-09-02");
  expect(requestCount).toBe(2);
});
