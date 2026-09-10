import type { StyleSpecification } from "maplibre-gl";

import type { MapLayer } from "./types";

export const MAP_BACKGROUND_COLOR = "#dfe7e8";
export const MAP_BASE_LAYER_ID = "xingxi-modern-base";
const FALLBACK_OSM_TILE_URL = "https://tile.openstreetmap.de/{z}/{x}/{y}.png";

function safeLayerKey(id: string) {
  return id.replace(/[^a-zA-Z0-9_-]/g, "-");
}

export function mapLayerSourceId(layer: Pick<MapLayer, "id">) {
  return `xingxi-map-source-${safeLayerKey(layer.id)}`;
}

export function mapLayerStyleId(layer: Pick<MapLayer, "id">) {
  return `xingxi-map-layer-${safeLayerKey(layer.id)}`;
}

export function getRenderableMapLayers(layers: MapLayer[]) {
  return layers.filter(
    (layer) => layer.available && Boolean(layer.tileUrl?.trim()),
  );
}

export function defaultMapLayerOpacity(layer: Pick<MapLayer, "kind">) {
  return layer.kind === "base" ? 1 : 0.46;
}

function rasterSource(layer: MapLayer) {
  return {
    type: "raster" as const,
    tiles: [layer.tileUrl!],
    tileSize: 256,
    attribution: layer.attribution,
  };
}

export function buildMapStyle(layers: MapLayer[]): StyleSpecification {
  const renderableLayers = getRenderableMapLayers(layers);
  const baseLayer = renderableLayers.find((layer) => layer.kind === "base");
  const historicalLayers = renderableLayers.filter(
    (layer) => layer.kind === "historical",
  );
  const sources: StyleSpecification["sources"] = {};
  const styleLayers: StyleSpecification["layers"] = [
    {
      id: "xingxi-map-background",
      type: "background",
      paint: { "background-color": MAP_BACKGROUND_COLOR },
    },
  ];

  if (baseLayer) {
    sources[mapLayerSourceId(baseLayer)] = rasterSource(baseLayer);
    styleLayers.push({
      id: MAP_BASE_LAYER_ID,
      type: "raster",
      source: mapLayerSourceId(baseLayer),
      paint: {
        "raster-opacity": 1,
        "raster-fade-duration": 0,
      },
    });
  } else {
    sources["xingxi-fallback-osm"] = {
      type: "raster",
      tiles: [FALLBACK_OSM_TILE_URL],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    };
    styleLayers.push({
      id: MAP_BASE_LAYER_ID,
      type: "raster",
      source: "xingxi-fallback-osm",
      paint: {
        "raster-opacity": 1,
        "raster-fade-duration": 0,
      },
    });
  }

  for (const layer of historicalLayers) {
    sources[mapLayerSourceId(layer)] = rasterSource(layer);
    styleLayers.push({
      id: mapLayerStyleId(layer),
      type: "raster",
      source: mapLayerSourceId(layer),
      layout: { visibility: "none" },
      paint: {
        "raster-opacity": defaultMapLayerOpacity(layer),
        "raster-fade-duration": 0,
      },
    });
  }

  return { version: 8, sources, layers: styleLayers };
}
