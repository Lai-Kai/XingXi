import { describe, expect, it } from "@rstest/core";

import {
  buildUncertaintyFeatureCollection,
  spatialExtentCoordinates,
} from "@/core/map/geometry";
import type { MapPoint } from "@/core/map/types";

const point = (overrides: Partial<MapPoint> = {}): MapPoint => ({
  id: "old-town",
  entityId: "place-old-town",
  name: "古镇旧址",
  entityType: "place",
  lon: 120.5,
  lat: 31.25,
  confidence: "approximate",
  basis: "方志里程与现代地名交叉定位",
  geometryType: "uncertainty_radius",
  uncertaintyRadiusMeters: 750,
  areaCoordinates: [],
  extentSource: "confidence_default",
  extentBasis: "按置信等级生成的范围，不代表统计概率。",
  coordinateSystem: "WGS84",
  dynasties: ["qing"],
  heritageStatus: "uncertain",
  accessStatus: "verify_before_visit",
  summary: "历史范围待考。",
  address: "历史地点",
  evidence: [],
  reviewStatus: "pending",
  releaseId: "release-1",
  recordKind: "corpus",
  startYear: null,
  endYear: null,
  ...overrides,
});

describe("historical map uncertainty geometry", () => {
  it("turns an uncertainty radius into a closed polygon instead of a point", () => {
    const coordinates = spatialExtentCoordinates(point());

    expect(coordinates.length).toBeGreaterThanOrEqual(33);
    expect(coordinates[0]).toEqual(coordinates.at(-1));
    expect(
      new Set(coordinates.map((item) => item.join(","))).size,
    ).toBeGreaterThan(8);
  });

  it("keeps evidence-backed historical polygons and excludes exact points", () => {
    const area = point({
      id: "historical-area",
      geometryType: "historical_area",
      uncertaintyRadiusMeters: null,
      areaCoordinates: [
        [120.49, 31.24],
        [120.51, 31.24],
        [120.51, 31.26],
        [120.49, 31.26],
        [120.49, 31.24],
      ],
      extentSource: "historical_map",
    });
    const exact = point({
      id: "modern-site",
      confidence: "exact",
      geometryType: "point",
      uncertaintyRadiusMeters: null,
      areaCoordinates: [],
      extentSource: null,
      extentBasis: null,
    });

    const collection = buildUncertaintyFeatureCollection(
      [area, exact],
      "historical-area",
    );

    expect(collection.features).toHaveLength(1);
    expect(collection.features[0]?.geometry.type).toBe("Polygon");
    expect(collection.features[0]?.properties).toMatchObject({
      id: "historical-area",
      selected: true,
      confidence: "approximate",
    });
  });

  it("hides all ranges by default and reveals only the requested range kind", () => {
    const historicalArea = point({
      id: "historical-area",
      geometryType: "historical_area",
      uncertaintyRadiusMeters: null,
      areaCoordinates: [
        [120.49, 31.24],
        [120.51, 31.24],
        [120.51, 31.26],
        [120.49, 31.26],
        [120.49, 31.24],
      ],
    });
    const speculativeArea = point({ id: "speculative-area" });

    const hidden = buildUncertaintyFeatureCollection(
      [historicalArea, speculativeArea],
      null,
      { showHistoricalRanges: false, showSpeculativeRanges: false },
    );
    const historical = buildUncertaintyFeatureCollection(
      [historicalArea, speculativeArea],
      null,
      { showHistoricalRanges: true, showSpeculativeRanges: false },
    );
    const speculative = buildUncertaintyFeatureCollection(
      [historicalArea, speculativeArea],
      null,
      { showHistoricalRanges: false, showSpeculativeRanges: true },
    );

    expect(hidden.features).toHaveLength(0);
    expect(historical.features.map((feature) => feature.properties.id)).toEqual(
      ["historical-area"],
    );
    expect(
      speculative.features.map((feature) => feature.properties.id),
    ).toEqual(["speculative-area"]);
  });

  it("keeps a selected place extent hidden while global range layers are off", () => {
    const collection = buildUncertaintyFeatureCollection(
      [point({ id: "selected" }), point({ id: "hidden" })],
      "selected",
      { showHistoricalRanges: false, showSpeculativeRanges: false },
    );

    expect(collection.features).toHaveLength(0);
  });

  it("marks a selected extent only after its range layer is enabled", () => {
    const collection = buildUncertaintyFeatureCollection(
      [point({ id: "selected" }), point({ id: "other" })],
      "selected",
      { showHistoricalRanges: false, showSpeculativeRanges: true },
    );

    expect(collection.features).toHaveLength(2);
    expect(collection.features[0]?.properties).toMatchObject({
      id: "selected",
      selected: true,
    });
  });
});
