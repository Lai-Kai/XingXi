import type { MapPoint } from "./types";

const EARTH_RADIUS_METERS = 6_371_008.8;

function degrees(value: number) {
  return (value * 180) / Math.PI;
}

function radians(value: number) {
  return (value * Math.PI) / 180;
}

function closeRing(coordinates: Array<[number, number]>) {
  if (coordinates.length === 0) return coordinates;
  const first = coordinates[0]!;
  const last = coordinates.at(-1)!;
  return first[0] === last[0] && first[1] === last[1]
    ? coordinates
    : [...coordinates, first];
}

function radiusRing(
  lon: number,
  lat: number,
  radiusMeters: number,
  segments = 64,
) {
  const angularDistance = radiusMeters / EARTH_RADIUS_METERS;
  const latitude = radians(lat);
  const longitude = radians(lon);
  const ring: Array<[number, number]> = [];
  for (let index = 0; index < segments; index += 1) {
    const bearing = (2 * Math.PI * index) / segments;
    const targetLatitude = Math.asin(
      Math.sin(latitude) * Math.cos(angularDistance) +
        Math.cos(latitude) * Math.sin(angularDistance) * Math.cos(bearing),
    );
    const targetLongitude =
      longitude +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(latitude),
        Math.cos(angularDistance) -
          Math.sin(latitude) * Math.sin(targetLatitude),
      );
    ring.push([degrees(targetLongitude), degrees(targetLatitude)]);
  }
  return closeRing(ring);
}

export function spatialExtentCoordinates(
  point: Pick<
    MapPoint,
    | "areaCoordinates"
    | "confidence"
    | "geometryType"
    | "lat"
    | "lon"
    | "uncertaintyRadiusMeters"
  >,
) {
  if (point.geometryType === "historical_area") {
    return closeRing(point.areaCoordinates);
  }
  if (point.geometryType === "uncertainty_radius") {
    const radius =
      point.uncertaintyRadiusMeters ??
      (point.confidence === "speculative" ? 2500 : 750);
    return radiusRing(point.lon, point.lat, radius);
  }
  return [];
}

export function buildUncertaintyFeatureCollection(
  points: MapPoint[],
  selectedId: string | null | undefined,
) {
  return {
    type: "FeatureCollection" as const,
    features: points.flatMap((point) => {
      const coordinates = spatialExtentCoordinates(point);
      if (coordinates.length < 4) return [];
      return [
        {
          type: "Feature" as const,
          properties: {
            confidence: point.confidence,
            geometryType: point.geometryType,
            id: point.id,
            name: point.name,
            selected: point.id === selectedId,
          },
          geometry: {
            type: "Polygon" as const,
            coordinates: [coordinates],
          },
        },
      ];
    }),
  };
}
