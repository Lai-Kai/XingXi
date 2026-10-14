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
  expect(requests.filter((url) => url.endsWith("/catalog"))).toHaveLength(1);
  expect(requests).toHaveLength(2);
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
  expect(requestCount).toBe(2);
});

test("forced map refresh bypasses and replaces the session cache", async () => {
  let requestCount = 0;
  rs.stubGlobal("fetch", async (url: string) => {
    if (url.includes("/reference-points")) return new Response("[]");
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

const reference = {
  id: "pt-yongan-bridge",
  entity_id: "entity-bridge-yongan",
  name: "永安桥",
  entity_type: "bridge",
  lon: 120.5043797,
  lat: 31.2540876,
  confidence: "approximate",
  basis: "地图原有近似定位",
  coordinate_system: "WGS84",
  dynasties: ["ming"],
  heritage_status: "extant",
  access_status: "view_only",
  summary: "参考景点",
  address: "严家花园前",
  evidence: [],
  record_kind: "reference",
  release_id: null,
  start_year: 1497,
  end_year: null,
};

const emptyCatalog = {
  updated_at: "unpublished",
  data_notice: "当前没有 active 知识版本，地图目录为空。",
  points: [],
  layers: [],
  events: [],
  relations: [],
  trajectories: [],
  routes: [],
};

test("an unpublished map adds only actual model references with original confidence", async () => {
  rs.stubGlobal(
    "fetch",
    async (url: string) =>
      new Response(
        JSON.stringify(
          url.includes("/reference-points")
            ? [
                reference,
                { ...reference, id: "unknown" },
                { ...reference, id: "corpus", record_kind: "corpus" },
              ]
            : emptyCatalog,
        ),
      ),
  );
  const catalog = await fetchMapCatalog();
  expect(catalog.updatedAt).toBe("unpublished");
  expect(catalog.points.map((point) => point.id)).toEqual(["pt-yongan-bridge"]);
  expect(catalog.points[0]!.confidence).toBe("approximate");
  expect(catalog.points[0]!.geometryType).toBe("uncertainty_radius");
  expect(catalog.points[0]!.releaseId).toBeNull();
  expect(catalog.events).toEqual([]);
  expect(catalog.dataNotice).toContain("独立三维模型参考点");
});

test("reference models never overwrite a released point or its review state", async () => {
  const released = {
    ...reference,
    record_kind: "corpus",
    release_id: "release-1",
    review_status: "disputed",
  };
  rs.stubGlobal(
    "fetch",
    async (url: string) =>
      new Response(
        JSON.stringify(
          url.includes("/reference-points")
            ? [reference]
            : { ...emptyCatalog, updated_at: "release-1", points: [released] },
        ),
      ),
  );
  const catalog = await fetchMapCatalog();
  expect(catalog.points).toHaveLength(1);
  expect(catalog.points[0]!.recordKind).toBe("corpus");
  expect(catalog.points[0]!.reviewStatus).toBe("disputed");
  expect(catalog.points[0]!.releaseId).toBe("release-1");
});

test("reference endpoint failure keeps the released catalog usable", async () => {
  rs.stubGlobal("fetch", async (url: string) => {
    if (url.includes("/reference-points")) throw new Error("offline");
    return new Response(JSON.stringify(emptyCatalog));
  });
  expect((await fetchMapCatalog()).points).toEqual([]);
});

test("a corrupted knowledge snapshot still fails closed", async () => {
  let requests = 0;
  rs.stubGlobal("fetch", async () => {
    requests += 1;
    return new Response("invalid snapshot", { status: 503 });
  });
  await expect(fetchMapCatalog()).rejects.toThrow("无法读取古舆地图资料");
  expect(requests).toBe(1);
});
