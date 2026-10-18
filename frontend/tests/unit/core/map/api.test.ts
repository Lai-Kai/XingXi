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
  expect(requests).toHaveLength(3);
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
  expect(requestCount).toBe(3);
});

test("forced map refresh bypasses and replaces the session cache", async () => {
  let requestCount = 0;
  rs.stubGlobal("fetch", async (url: string) => {
    if (url.includes("/reference-")) return new Response("[]");
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

const referenceEvent = {
  id: "event-yongan-built",
  title: "永安桥始建",
  year_start: 1497,
  year_end: 1497,
  time_label: "明弘治十年（1497）",
  precision: "exact",
  point_id: "pt-yongan-bridge",
  summary: "景点条目记载的建桥年代。",
  record_kind: "reference",
  release_id: null,
  review_status: null,
  featured: true,
  importance: "landmark",
  evidence: [
    {
      id: "reference-evidence",
      title: "永安桥条目",
      publisher: "公开景点资料",
      url: "https://example.test/yongan",
      kind: "historical_reference",
      note: "仍需文献复核",
    },
  ],
};

test("an empty released timeline includes separately sourced reference events", async () => {
  rs.stubGlobal("fetch", async (url: string) => {
    if (url.includes("/reference-points")) return Response.json([reference]);
    if (url.includes("/reference-events"))
      return Response.json([referenceEvent]);
    return Response.json({ ...emptyCatalog, updated_at: "release-1" });
  });
  const catalog = await fetchMapCatalog();
  expect(catalog.events).toHaveLength(1);
  expect(catalog.events[0]).toMatchObject({
    id: referenceEvent.id,
    yearStart: 1497,
    pointId: reference.id,
    recordKind: "reference",
    releaseId: null,
    reviewStatus: null,
  });
  expect(catalog.events[0]!.evidence[0]!.url).toBe(
    referenceEvent.evidence[0]!.url,
  );
  expect(catalog.dataNotice).toContain("景点参考事件");
});

test("reference timeline supplementation preserves released event identity and review state", async () => {
  const released = {
    ...referenceEvent,
    record_kind: "corpus",
    release_id: "release-1",
    review_status: "disputed",
    title: "版本中的事件",
  };
  rs.stubGlobal("fetch", async (url: string) => {
    if (url.includes("/reference-points")) return Response.json([reference]);
    if (url.includes("/reference-events"))
      return Response.json([referenceEvent]);
    return Response.json({
      ...emptyCatalog,
      updated_at: "release-1",
      events: [released],
    });
  });
  const catalog = await fetchMapCatalog();
  expect(catalog.events).toHaveLength(1);
  expect(catalog.events[0]).toMatchObject({
    title: released.title,
    recordKind: "corpus",
    reviewStatus: "disputed",
    releaseId: "release-1",
  });
});

test("reference events require an exact reference point, provenance and no release claim", async () => {
  rs.stubGlobal("fetch", async (url: string) => {
    if (url.includes("/reference-points")) return Response.json([reference]);
    if (url.includes("/reference-events"))
      return Response.json([
        { ...referenceEvent, id: "unknown", point_id: "unknown" },
        { ...referenceEvent, id: "no-evidence", evidence: [] },
        { ...referenceEvent, id: "wrong-kind", record_kind: "corpus" },
        {
          ...referenceEvent,
          id: "wrong-release",
          release_id: "forged-release",
        },
      ]);
    return Response.json(emptyCatalog);
  });
  expect((await fetchMapCatalog()).events).toEqual([]);
});

test("a reference event outage does not discard the map or its existing events", async () => {
  rs.stubGlobal("fetch", async (url: string) => {
    if (url.includes("/reference-points")) return Response.json([reference]);
    if (url.includes("/reference-events"))
      return new Response("Not found", { status: 404 });
    return Response.json({ ...emptyCatalog, events: [referenceEvent] });
  });
  expect((await fetchMapCatalog()).events.map((event) => event.id)).toEqual([
    referenceEvent.id,
  ]);
});
