import { afterEach, expect, rs, test } from "@rstest/core";

import { createMapPoint, fetchCustomMapPoints } from "@/core/map/api";

afterEach(() => {
  rs.unstubAllGlobals();
});

const raw = {
  id: "custom-point-1",
  entity_id: "custom-place-1",
  name: "研习点",
  lon: 120.5,
  lat: 31.2,
  entity_type: "place",
  confidence: "exact",
  coordinate_system: "WGS84",
  basis: "地图选点",
  dynasties: [],
  heritage_status: "uncertain",
  access_status: "verify_before_visit",
  evidence: [],
  record_kind: "custom",
  start_year: null,
  end_year: null,
};

test("custom locations use authenticated uncached reads with explicit manual origin", async () => {
  rs.stubGlobal("fetch", async (_url: string, init: RequestInit) => {
    expect(init.cache).toBe("no-store");
    expect(init.credentials).toBe("include");
    return new Response(JSON.stringify([raw]));
  });
  const [point] = await fetchCustomMapPoints();
  expect(point).toMatchObject({
    id: raw.id,
    entityId: raw.entity_id,
    recordKind: "custom",
    evidence: [],
    releaseId: null,
  });
});

test("creation sends the name exact coordinates and stable request key", async () => {
  const input = { name: "研习点", lon: 120.5, lat: 31.2, request_id: "same" };
  rs.stubGlobal("fetch", async (_url: string, init: RequestInit) => {
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(input);
    return new Response(JSON.stringify(raw), { status: 201 });
  });
  const point = await createMapPoint(input, new AbortController().signal);
  expect(point.lon).toBe(input.lon);
  expect(point.lat).toBe(input.lat);
});

test("save errors remain actionable and do not return a phantom location", async () => {
  rs.stubGlobal(
    "fetch",
    async () =>
      new Response(JSON.stringify({ detail: "仅管理员可创建点位" }), {
        status: 403,
      }),
  );
  await expect(
    createMapPoint(
      { name: "研习点", lon: 120.5, lat: 31.2, request_id: "same" },
      new AbortController().signal,
    ),
  ).rejects.toThrow("仅管理员可创建点位");
});
