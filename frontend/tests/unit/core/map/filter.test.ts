import { describe, expect, it } from "@rstest/core";

import { filterMapPoints, type MapPoint } from "@/core/map/types";

const basePoint: MapPoint = {
  id: "xiangxi",
  entityId: "entity-xiangxi",
  name: "香溪历史街区",
  entityType: "historic_district",
  lon: 120.5,
  lat: 31.25,
  confidence: "exact",
  basis: "published current map feature",
  geometryType: "point",
  uncertaintyRadiusMeters: null,
  areaCoordinates: [],
  extentSource: null,
  extentBasis: null,
  coordinateSystem: "WGS84",
  dynasties: ["modern"],
  heritageStatus: "extant",
  accessStatus: "public_space",
  summary: "当前地物",
  address: "木渎镇",
  evidence: [],
  reviewStatus: null,
  releaseId: null,
  recordKind: "reference",
  startYear: null,
  endYear: null,
};

describe("filterMapPoints", () => {
  it("filters by entity type and confidence", () => {
    const approximate = {
      ...basePoint,
      id: "bridge",
      entityType: "bridge",
      confidence: "approximate" as const,
    };
    const points = filterMapPoints([basePoint, approximate], {
      entityTypes: ["historic_district"],
      minConfidence: "exact",
    });
    expect(points.map((point) => point.id)).toEqual(["xiangxi"]);
  });

  it("filters by Chinese query text", () => {
    expect(filterMapPoints([basePoint], { query: "香溪" })).toHaveLength(1);
  });
});
