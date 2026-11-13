import { afterEach, expect, rs, test } from "@rstest/core";

import { type MapCatalog, type MapPoint } from "@/core/map/types";

const points: MapPoint[] = (
  [
    ["pt-yongan-bridge", "entity-bridge-yongan", "永安桥"],
    ["pt-mingyue-temple", "entity-temple-mingyue", "明月古寺"],
    ["pt-hongyin", "entity-garden-hongyin", "虹饮山房"],
    ["pt-gusong-garden", "entity-garden-gusong", "古松园"],
  ] as const
).map(([id, entityId, name]) => ({
  id,
  entityId,
  name,
  entityType: "place",
  lon: 120.5,
  lat: 31.25,
  confidence: "approximate",
  basis: "Test reference location",
  geometryType: "point",
  uncertaintyRadiusMeters: null,
  areaCoordinates: [],
  extentSource: null,
  extentBasis: null,
  coordinateSystem: "WGS84",
  dynasties: [],
  heritageStatus: "extant",
  accessStatus: "verify_before_visit",
  summary: "Test point",
  address: "Test address",
  recordKind: "reference",
  reviewStatus: null,
  releaseId: null,
  evidence: [],
  startYear: null,
  endYear: null,
}));

const catalog: MapCatalog = {
  updatedAt: "release-2",
  dataNotice: "已发布资料",
  points,
  layers: [],
  events: [],
  relations: [],
  trajectories: [],
  routes: [],
};

async function mount(initialCatalog: MapCatalog | null = catalog) {
  let slot = 0;
  const values: unknown[] = [];
  rs.resetModules();
  rs.doMock("react", () => ({
    useState: (initial: unknown) => {
      const index = slot++;
      if (!(index in values)) values[index] = initial;
      return [
        values[index],
        (value: unknown) => {
          values[index] =
            typeof value === "function" ? value(values[index]) : value;
        },
      ];
    },
    useMemo: (compute: () => unknown) => compute(),
  }));
  const { useStudyRoutes: invokeRoutes } =
    await import("@/core/map/use-study-routes");
  let currentCatalog = initialCatalog;
  return {
    render(nextCatalog = currentCatalog) {
      currentCatalog = nextCatalog;
      slot = 0;
      return invokeRoutes(currentCatalog);
    },
  };
}

afterEach(() => {
  rs.doUnmock("react");
  rs.resetModules();
});

test("an empty Release route catalog starts with an explicitly labelled, bound example", async () => {
  const page = await mount(null);
  expect(page.render().activeRoute).toBeNull();
  const loaded = page.render(catalog);
  expect(loaded.activeRoute?.name).toBe("木渎古镇人文半日研学（示例）");
  expect(loaded.isExample).toBe(true);
  expect(loaded.routeStops).toEqual(points);
  expect(catalog.routes).toEqual([]);
});

test("example stops require exact reference identity and never invent missing points", async () => {
  const page = await mount({
    ...catalog,
    points: [
      points[0]!,
      { ...points[1]!, entityId: "another-entity" },
      { ...points[2]!, recordKind: "corpus", releaseId: "release-2" },
    ],
  });
  expect(page.render().routeStops).toEqual([points[0]]);
});

test("a catalog with no points still has an editable template with no fabricated stops", async () => {
  const page = await mount({ ...catalog, points: [] });
  expect(page.render().activeRoute).not.toBeNull();
  expect(page.render().routeStops).toEqual([]);
  expect(page.render().availableStops).toEqual([]);
});

test("readers can reorder, remove, re-add and restore the example", async () => {
  const page = await mount();
  page.render().moveStop(points[0]!.id, 1);
  expect(page.render().routeStops.map((point) => point.id)).toEqual([
    points[1]!.id,
    points[0]!.id,
    points[2]!.id,
    points[3]!.id,
  ]);
  page.render().removeStop(points[0]!.id);
  expect(page.render().availableStops).toEqual([points[0]]);
  page.render().addStop(points[0]!.id);
  expect(page.render().routeStops.at(-1)).toEqual(points[0]);
  page.render().addStop(points[0]!.id);
  page.render().addStop("unknown-point");
  expect(page.render().routeStops).toHaveLength(4);
  page.render().resetRoute();
  expect(page.render().routeStops).toEqual(points);
});

test("removing all stops survives a custom-point refresh and permits adding a new stop", async () => {
  const page = await mount();
  points.forEach((point) => page.render().removeStop(point.id));
  const customPoint = {
    ...points[0]!,
    id: "custom-1",
    entityId: "custom-entity-1",
    recordKind: "custom" as const,
  };
  expect(
    page.render({ ...catalog, points: [...points, customPoint] }).routeStops,
  ).toEqual([]);
  page.render().addStop(customPoint.id);
  expect(page.render().routeStops).toEqual([customPoint]);
});

test("supplied routes take priority and editing works when their stops are missing", async () => {
  const route = {
    id: "published-route",
    name: "既有路线",
    duration: "half_day" as const,
    audience: "学生",
    summary: "观察",
    stopIds: ["missing", points[0]!.id, points[1]!.id],
    disclaimer: "出发前核验",
    evidence: [],
  };
  const page = await mount({
    ...catalog,
    routes: [route, { ...route, id: "second", stopIds: [points[3]!.id] }],
  });
  expect(page.render().isExample).toBe(false);
  expect(page.render().routes).toHaveLength(2);
  page.render().moveStop(points[1]!.id, -1);
  expect(page.render().routeStops).toEqual([points[1], points[0]]);
  page.render().selectRoute("second");
  expect(page.render().routeStops).toEqual([points[3]]);
});
