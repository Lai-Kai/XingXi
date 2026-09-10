export type SpatialConfidence = "exact" | "approximate" | "speculative";
export type SpatialGeometryType =
  | "point"
  | "uncertainty_radius"
  | "historical_area";
export type SpatialExtentSource =
  | "evidence"
  | "historical_map"
  | "editorial_estimate"
  | "confidence_default";
export type DynastyLayer =
  | "spring_autumn"
  | "jin"
  | "liang"
  | "tang"
  | "song"
  | "ming"
  | "qing"
  | "modern";
export type HeritageStatus = "extant" | "site" | "uncertain";
export type AccessStatus =
  | "public_space"
  | "ticket_or_hours"
  | "religious_site"
  | "view_only"
  | "verify_before_visit";
export type MapReviewStatus = "pending" | "reviewed" | "disputed" | "rejected";
export type MapRecordScope = "formal" | "draft";

export type MapEvidence = {
  id: string;
  title: string;
  publisher: string;
  url: string;
  kind:
    | "current_map"
    | "historical_reference"
    | "catalog_reference"
    | "corpus_evidence";
  retrievedAt: string;
  note: string;
  quote?: string | null;
  media?: MapEvidenceMedia[];
};

export type MapEvidenceMedia = {
  url: string;
  mediaType: "image" | "document_page" | "model";
  caption: string;
};

export type MapEntityReference = {
  id: string;
  name: string;
  entityType: string;
};

export type MapPoint = {
  id: string;
  entityId: string;
  name: string;
  entityType: string;
  lon: number;
  lat: number;
  confidence: SpatialConfidence;
  basis: string;
  geometryType: SpatialGeometryType;
  uncertaintyRadiusMeters: number | null;
  areaCoordinates: Array<[number, number]>;
  extentSource: SpatialExtentSource | null;
  extentBasis: string | null;
  coordinateSystem: "WGS84";
  dynasties: DynastyLayer[];
  heritageStatus: HeritageStatus;
  accessStatus: AccessStatus;
  summary: string;
  address: string;
  evidence: MapEvidence[];
  reviewStatus: MapReviewStatus | null;
  releaseId: string | null;
  recordKind: "reference" | "corpus";
  startYear: number | null;
  endYear: number | null;
};

export type MapLayer = {
  id: string;
  name: string;
  kind: "base" | "historical";
  available: boolean;
  sourceUrl: string;
  attribution: string;
  calibrationNote: string;
  tileUrl: string | null;
};

export type TimelineEvent = {
  id: string;
  title: string;
  yearStart: number | null;
  yearEnd: number | null;
  timeLabel: string;
  precision: "exact" | "period" | "unknown";
  pointId: string;
  summary: string;
  evidence: MapEvidence[];
  reviewStatus: MapReviewStatus | null;
  releaseId: string | null;
  recordKind: "reference" | "corpus";
  featured: boolean;
  importance: "landmark" | "notable" | "context";
  participants?: MapEntityReference[];
};

export type MapRelation = {
  id: string;
  subjectId: string;
  subjectName: string;
  subjectType: string;
  relationType: string;
  objectId: string;
  objectName: string;
  objectType: string;
  startTime: string | null;
  endTime: string | null;
  confidence: number;
  evidence: MapEvidence[];
  reviewStatus: MapReviewStatus | null;
  releaseId: string | null;
  recordKind: "reference" | "corpus";
};

export type TrajectoryPoint = {
  id: string;
  pointId: string;
  yearStart: number | null;
  yearEnd: number | null;
  timeLabel: string;
  label: string;
  confidence: SpatialConfidence;
  evidence: MapEvidence[];
  reviewStatus: MapReviewStatus | null;
  sourceRecordId: string | null;
};

export type PersonTrajectory = {
  id: string;
  personId: string;
  personName: string;
  summary: string;
  hasUncertainSegments: boolean;
  disclaimer: string;
  points: TrajectoryPoint[];
  reviewStatus: MapReviewStatus | null;
  releaseId: string | null;
  recordKind: "reference" | "corpus";
};

export type MapRoute = {
  id: string;
  name: string;
  duration: "half_day" | "full_day";
  audience: string;
  summary: string;
  stopIds: string[];
  disclaimer: string;
  evidence: MapEvidence[];
};

export type MapCatalog = {
  updatedAt: string;
  dataNotice: string;
  points: MapPoint[];
  layers: MapLayer[];
  events: TimelineEvent[];
  relations: MapRelation[];
  trajectories: PersonTrajectory[];
  routes: MapRoute[];
};

export type UserMapLocation = {
  lon: number;
  lat: number;
  accuracyMeters: number;
};

export type PlannedMapRoute = {
  profile: "driving";
  coordinates: Array<[number, number]>;
  distanceMeters: number | null;
  durationSeconds: number | null;
  provider: string;
  routingStatus: "routed" | "unavailable";
  routeKind: "road" | "stop_order";
  message: string;
};

export type MapFilter = {
  entityTypes?: string[];
  dynasties?: DynastyLayer[];
  minConfidence?: SpatialConfidence;
  heritageStatuses?: HeritageStatus[];
  query?: string;
  year?: number;
  includeUnknownTime?: boolean;
  recordScopes?: MapRecordScope[];
};

const confidenceRank: Record<SpatialConfidence, number> = {
  exact: 3,
  approximate: 2,
  speculative: 1,
};

export function filterMapPoints(
  points: MapPoint[],
  filter: MapFilter = {},
): MapPoint[] {
  return points.filter((point) => {
    if (filter.recordScopes?.length) {
      const scope: MapRecordScope =
        point.recordKind === "corpus" && point.reviewStatus !== "reviewed"
          ? "draft"
          : "formal";
      if (!filter.recordScopes.includes(scope)) return false;
    }
    if (
      filter.entityTypes?.length &&
      !filter.entityTypes.includes(point.entityType)
    ) {
      return false;
    }
    if (
      filter.dynasties?.length &&
      !point.dynasties.some((dynasty) => filter.dynasties!.includes(dynasty))
    ) {
      return false;
    }
    if (
      filter.minConfidence &&
      confidenceRank[point.confidence] < confidenceRank[filter.minConfidence]
    ) {
      return false;
    }
    if (
      filter.heritageStatuses?.length &&
      !filter.heritageStatuses.includes(point.heritageStatus)
    ) {
      return false;
    }
    if (filter.query?.trim()) {
      const query = filter.query.trim().toLocaleLowerCase();
      if (
        !`${point.name} ${point.summary} ${point.address}`
          .toLocaleLowerCase()
          .includes(query)
      ) {
        return false;
      }
    }
    if (filter.year !== undefined) {
      if (point.startYear === null) {
        if (!filter.includeUnknownTime) return false;
      } else if (
        filter.year < point.startYear ||
        (point.endYear !== null && filter.year > point.endYear)
      ) {
        return false;
      }
    }
    return true;
  });
}

export function filterTimelineEvents(
  events: TimelineEvent[],
  year: number,
): TimelineEvent[] {
  return events.filter((event) => {
    if (event.yearStart === null) return false;
    const end = event.yearEnd ?? event.yearStart;
    return event.yearStart <= year && end >= year;
  });
}

export function eventsUpToYear(
  events: TimelineEvent[],
  year: number,
): TimelineEvent[] {
  return events.filter(
    (event) => event.yearStart === null || event.yearStart <= year,
  );
}

export function featuredTimelineEvents(
  events: TimelineEvent[],
): TimelineEvent[] {
  return events
    .filter((event) => event.featured && event.yearStart !== null)
    .sort((left, right) => {
      return (
        left.yearStart! - right.yearStart! ||
        left.id.localeCompare(right.id, "zh-CN")
      );
    });
}

export function nextTimelineEventIndex(
  events: TimelineEvent[],
  activeEventId: string | null,
): number {
  if (events.length === 0) return -1;
  const currentIndex = events.findIndex((event) => event.id === activeEventId);
  return currentIndex < 0 || currentIndex === events.length - 1
    ? 0
    : currentIndex + 1;
}

export function timelineEventsForPoint(
  events: TimelineEvent[],
  pointId: string,
): TimelineEvent[] {
  return events
    .filter((event) => event.pointId === pointId)
    .sort((left, right) => {
      if (left.yearStart === null) return 1;
      if (right.yearStart === null) return -1;
      return (
        left.yearStart - right.yearStart ||
        left.title.localeCompare(right.title, "zh-CN")
      );
    });
}

export function buildStudyRoute(
  points: MapPoint[],
  route: Pick<MapRoute, "stopIds">,
): MapPoint[] {
  const byId = new Map(points.map((point) => [point.id, point]));
  return route.stopIds
    .map((id) => byId.get(id))
    .filter((point): point is MapPoint => Boolean(point));
}
