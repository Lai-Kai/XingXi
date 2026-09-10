import { describe, expect, it } from "@rstest/core";

import {
  buildStudyRoute,
  type MapPoint,
  type MapRoute,
} from "@/core/map/types";

const point = (id: string): MapPoint => ({
  id,
  entityId: `entity-${id}`,
  name: id,
  entityType: "place",
  lon: 120.5,
  lat: 31.25,
  confidence: "exact",
  basis: "test",
  geometryType: "point",
  uncertaintyRadiusMeters: null,
  areaCoordinates: [],
  extentSource: null,
  extentBasis: null,
  coordinateSystem: "WGS84",
  dynasties: ["modern"],
  heritageStatus: "extant",
  accessStatus: "public_space",
  summary: "test",
  address: "test",
  evidence: [],
  reviewStatus: null,
  releaseId: null,
  recordKind: "reference",
  startYear: null,
  endYear: null,
});

describe("buildStudyRoute", () => {
  it("orders route stops and ignores unavailable records", () => {
    const route: Pick<MapRoute, "stopIds"> = {
      stopIds: ["second", "missing", "first"],
    };
    expect(
      buildStudyRoute([point("first"), point("second")], route).map(
        (p) => p.id,
      ),
    ).toEqual(["second", "first"]);
  });
});
