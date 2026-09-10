import type { StyleSpecification } from "maplibre-gl";

import type { MapLayer } from "./types";

export const MAP_BACKGROUND_COLOR = "#ebe6d8";
export const MAP_BASE_LAYER_ID = "xingxi-modern-base";
const FALLBACK_OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

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
  return layer.kind === "base" ? 0.26 : 0.46;
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
      id: "xingxi-history-paper",
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
        "raster-opacity": defaultMapLayerOpacity(baseLayer),
        "raster-saturation": -1,
        "raster-contrast": -0.12,
        "raster-brightness-min": 0.58,
        "raster-brightness-max": 0.96,
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
        "raster-opacity": 0.26,
        "raster-saturation": -1,
        "raster-contrast": -0.12,
        "raster-brightness-min": 0.58,
        "raster-brightness-max": 0.96,
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
      paint: {
        "raster-opacity": defaultMapLayerOpacity(layer),
        "raster-saturation": -0.18,
        "raster-fade-duration": 0,
      },
    });
  }

  return { version: 8, sources, layers: styleLayers };
}
