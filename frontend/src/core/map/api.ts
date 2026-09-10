import { getBackendBaseURL } from "@/core/config";

import {
  type MapCatalog,
  type MapEvidence,
  type MapLayer,
  type MapRelation,
  type MapPoint,
  type MapRoute,
  type PersonTrajectory,
  type PlannedMapRoute,
  type TimelineEvent,
} from "./types";

type RawEvidence = Omit<MapEvidence, "retrievedAt" | "media"> & {
  retrieved_at: string;
  media?: Array<{
    url: string;
    media_type: NonNullable<MapEvidence["media"]>[number]["mediaType"];
    caption: string;
  }>;
};
type RawEntityReference = {
  id: string;
  name: string;
  entity_type: string;
};
type RawRelation = Omit<
  MapRelation,
  | "subjectId"
  | "subjectName"
  | "subjectType"
  | "relationType"
  | "objectId"
  | "objectName"
  | "objectType"
  | "startTime"
  | "endTime"
  | "reviewStatus"
  | "releaseId"
  | "recordKind"
  | "participants"
  | "evidence"
> & {
  subject_id: string;
  subject_name: string;
  subject_type: string;
  relation_type: string;
  object_id: string;
  object_name: string;
  object_type: string;
  start_time: string | null;
  end_time: string | null;
  review_status?: MapRelation["reviewStatus"];
  release_id?: string | null;
  record_kind?: MapRelation["recordKind"];
  evidence: RawEvidence[];
};
type RawPoint = Omit<
  MapPoint,
  | "entityId"
  | "entityType"
  | "coordinateSystem"
  | "heritageStatus"
  | "accessStatus"
  | "startYear"
  | "endYear"
  | "reviewStatus"
  | "releaseId"
  | "recordKind"
  | "geometryType"
  | "uncertaintyRadiusMeters"
  | "areaCoordinates"
  | "extentSource"
  | "extentBasis"
  | "evidence"
> & {
  entity_id: string;
  entity_type: string;
  coordinate_system: "WGS84";
  heritage_status: MapPoint["heritageStatus"];
  access_status: MapPoint["accessStatus"];
  start_year: number | null;
  end_year: number | null;
  review_status?: MapPoint["reviewStatus"];
  release_id?: string | null;
  record_kind?: MapPoint["recordKind"];
  geometry_type?: MapPoint["geometryType"];
  uncertainty_radius_m?: number | null;
  area_coordinates?: Array<[number, number]>;
  extent_source?: MapPoint["extentSource"];
  extent_basis?: string | null;
  evidence: RawEvidence[];
};
type RawLayer = Omit<MapLayer, "sourceUrl" | "calibrationNote" | "tileUrl"> & {
  source_url: string;
  calibration_note: string;
  tile_url: string | null;
};
type RawEvent = Omit<
  TimelineEvent,
  | "yearStart"
  | "yearEnd"
  | "timeLabel"
  | "pointId"
  | "reviewStatus"
  | "releaseId"
  | "recordKind"
  | "participants"
  | "evidence"
> & {
  year_start: number | null;
  year_end: number | null;
  time_label: string;
  point_id: string;
  review_status?: TimelineEvent["reviewStatus"];
  release_id?: string | null;
  record_kind?: TimelineEvent["recordKind"];
  featured?: boolean;
  importance?: TimelineEvent["importance"];
  participants?: RawEntityReference[];
  evidence: RawEvidence[];
};
type RawTrajectory = {
  id: string;
  person_id: string;
  person_name: string;
  summary: string;
  has_uncertain_segments: boolean;
  disclaimer: string;
  review_status?: PersonTrajectory["reviewStatus"];
  release_id?: string | null;
  record_kind?: PersonTrajectory["recordKind"];
  points: Array<{
    id: string;
    point_id: string;
    year_start: number | null;
    year_end: number | null;
    time_label: string;
    label: string;
    confidence: PersonTrajectory["points"][number]["confidence"];
    evidence: RawEvidence[];
    review_status?: PersonTrajectory["points"][number]["reviewStatus"];
    source_record_id?: string | null;
  }>;
};
type RawRoute = Omit<MapRoute, "stopIds" | "evidence"> & {
  stop_ids: string[];
  evidence: RawEvidence[];
};
type RawCatalog = {
  updated_at: string;
  data_notice: string;
  points: RawPoint[];
  layers: RawLayer[];
  events: RawEvent[];
  relations?: RawRelation[];
  trajectories: RawTrajectory[];
  routes: RawRoute[];
};

function evidence(raw: RawEvidence): MapEvidence {
  return {
    ...raw,
    retrievedAt: raw.retrieved_at,
    quote: raw.quote ?? null,
    media: (raw.media ?? []).map((media) => ({
      url: media.url,
      mediaType: media.media_type,
      caption: media.caption,
    })),
  };
}

function point(raw: RawPoint): MapPoint {
  const geometryType =
    raw.geometry_type ??
    (raw.confidence === "exact" ? "point" : "uncertainty_radius");
  return {
    id: raw.id,
    entityId: raw.entity_id,
    name: raw.name,
    entityType: raw.entity_type,
    lon: raw.lon,
    lat: raw.lat,
    confidence: raw.confidence,
    basis: raw.basis,
    geometryType,
    uncertaintyRadiusMeters:
      raw.uncertainty_radius_m ??
      (geometryType === "uncertainty_radius"
        ? raw.confidence === "speculative"
          ? 2500
          : 750
        : null),
    areaCoordinates: raw.area_coordinates ?? [],
    extentSource:
      raw.extent_source ??
      (geometryType === "point" ? null : "confidence_default"),
    extentBasis:
      raw.extent_basis ??
      (geometryType === "point"
        ? null
        : "按空间置信等级生成的可视化包络，不代表历史边界或统计概率。"),
    coordinateSystem: raw.coordinate_system,
    dynasties: raw.dynasties,
    heritageStatus: raw.heritage_status,
    accessStatus: raw.access_status,
    summary: raw.summary,
    address: raw.address,
    evidence: raw.evidence.map(evidence),
    reviewStatus: raw.review_status ?? null,
    releaseId: raw.release_id ?? null,
    recordKind: raw.record_kind ?? "reference",
    startYear: raw.start_year,
    endYear: raw.end_year,
  };
}

export async function fetchMapCatalog(
  signal?: AbortSignal,
): Promise<MapCatalog> {
  const response = await fetch(`${getBackendBaseURL()}/api/map/catalog`, {
    signal,
    cache: "no-store",
  });
  if (!response.ok) throw new Error("无法读取古舆地图资料");
  const raw = (await response.json()) as RawCatalog;
  return {
    updatedAt: raw.updated_at,
    dataNotice: raw.data_notice,
    points: raw.points.map(point),
    layers: raw.layers.map((layer) => ({
      id: layer.id,
      name: layer.name,
      kind: layer.kind,
      available: layer.available,
      sourceUrl: layer.source_url,
      attribution: layer.attribution,
      calibrationNote: layer.calibration_note,
      tileUrl: layer.tile_url,
    })),
    events: raw.events.map((eventItem) => ({
      id: eventItem.id,
      title: eventItem.title,
      yearStart: eventItem.year_start,
      yearEnd: eventItem.year_end,
      timeLabel: eventItem.time_label,
      precision: eventItem.precision,
      pointId: eventItem.point_id,
      summary: eventItem.summary,
      evidence: eventItem.evidence.map(evidence),
      reviewStatus: eventItem.review_status ?? null,
      releaseId: eventItem.release_id ?? null,
      recordKind: eventItem.record_kind ?? "reference",
      featured: eventItem.featured ?? false,
      importance: eventItem.importance ?? "context",
      participants: (eventItem.participants ?? []).map((participant) => ({
        id: participant.id,
        name: participant.name,
        entityType: participant.entity_type,
      })),
    })),
    relations: (raw.relations ?? []).map((relation) => ({
      id: relation.id,
      subjectId: relation.subject_id,
      subjectName: relation.subject_name,
      subjectType: relation.subject_type,
      relationType: relation.relation_type,
      objectId: relation.object_id,
      objectName: relation.object_name,
      objectType: relation.object_type,
      startTime: relation.start_time,
      endTime: relation.end_time,
      confidence: relation.confidence,
      evidence: relation.evidence.map(evidence),
      reviewStatus: relation.review_status ?? null,
      releaseId: relation.release_id ?? null,
      recordKind: relation.record_kind ?? "reference",
    })),
    trajectories: raw.trajectories.map((trajectory) => ({
      id: trajectory.id,
      personId: trajectory.person_id,
      personName: trajectory.person_name,
      summary: trajectory.summary,
      hasUncertainSegments: trajectory.has_uncertain_segments,
      disclaimer: trajectory.disclaimer,
      reviewStatus: trajectory.review_status ?? null,
      releaseId: trajectory.release_id ?? null,
      recordKind: trajectory.record_kind ?? "reference",
      points: trajectory.points.map((trajectoryPoint) => ({
        id: trajectoryPoint.id,
        pointId: trajectoryPoint.point_id,
        yearStart: trajectoryPoint.year_start,
        yearEnd: trajectoryPoint.year_end,
        timeLabel: trajectoryPoint.time_label,
        label: trajectoryPoint.label,
        confidence: trajectoryPoint.confidence,
        evidence: trajectoryPoint.evidence.map(evidence),
        reviewStatus: trajectoryPoint.review_status ?? null,
        sourceRecordId: trajectoryPoint.source_record_id ?? null,
      })),
    })),
    routes: raw.routes.map((route) => ({
      id: route.id,
      name: route.name,
      duration: route.duration,
      audience: route.audience,
      summary: route.summary,
      stopIds: route.stop_ids,
      disclaimer: route.disclaimer,
      evidence: route.evidence.map(evidence),
    })),
  };
}

export async function planMapRoute(
  points: Array<{ lon: number; lat: number; name?: string }>,
): Promise<PlannedMapRoute> {
  const response = await fetch(`${getBackendBaseURL()}/api/map/route-plan`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ coordinates: points, profile: "driving" }),
  });
  if (!response.ok) throw new Error("无法计算道路路线");
  const raw = (await response.json()) as {
    profile: "driving";
    coordinates: Array<[number, number]>;
    distance_meters: number | null;
    duration_seconds: number | null;
    provider: string;
    routing_status: "routed" | "unavailable";
    route_kind: "road" | "stop_order";
    message: string;
  };
  return {
    profile: raw.profile,
    coordinates: raw.coordinates,
    distanceMeters: raw.distance_meters,
    durationSeconds: raw.duration_seconds,
    provider: raw.provider,
    routingStatus: raw.routing_status,
    routeKind: raw.route_kind,
    message: raw.message,
  };
}
