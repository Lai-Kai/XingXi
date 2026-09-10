import { describe, expect, it } from "@rstest/core";

import {
  buildMapStyle,
  getRenderableMapLayers,
  mapLayerSourceId,
  mapLayerStyleId,
} from "@/core/map/layers";
import type { MapLayer } from "@/core/map/types";

const layer = (overrides: Partial<MapLayer> = {}): MapLayer => ({
  id: "osm-current",
  name: "现代底图",
  kind: "base",
  available: true,
  sourceUrl: "https://www.openstreetmap.org/copyright",
  attribution: "© OpenStreetMap contributors",
  calibrationNote: "仅用于现状定位。",
  tileUrl: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  ...overrides,
});

describe("古今对照地图图层", () => {
  it("弱化现代底图，并把可用历史图层作为半透明叠加层", () => {
    const historical = layer({
      id: "song-water-system",
      name: "宋代水系校准图",
      kind: "historical",
      tileUrl: "https://example.test/song/{z}/{x}/{y}.png",
    });
    const style = buildMapStyle([layer(), historical]);
    const base = style.layers.find((item) => item.id === "xingxi-modern-base");
    const historicalLayer = style.layers.find(
      (item) => item.id === mapLayerStyleId(historical),
    );

    expect(base).toMatchObject({
      type: "raster",
      paint: {
        "raster-opacity": 0.26,
        "raster-saturation": -1,
      },
    });
    expect(historicalLayer).toMatchObject({
      type: "raster",
      source: mapLayerSourceId(historical),
      paint: { "raster-opacity": 0.46 },
    });
    expect(style.sources).toHaveProperty(mapLayerSourceId(historical));
  });

  it("不会为待校准历史图层创建地图资源", () => {
    const unavailable = layer({
      id: "pingjiang-map-reference",
      kind: "historical",
      available: false,
      tileUrl: null,
    });
    const style = buildMapStyle([layer(), unavailable]);

    expect(getRenderableMapLayers([layer(), unavailable])).toEqual([layer()]);
    expect(style.sources).not.toHaveProperty(mapLayerSourceId(unavailable));
    expect(style.layers).not.toContainEqual(
      expect.objectContaining({ id: mapLayerStyleId(unavailable) }),
    );
  });
});
