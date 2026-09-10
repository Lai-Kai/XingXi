import { describe, expect, it } from "@rstest/core";

import {
  featuredTimelineEvents,
  filterMapPoints,
  filterTimelineEvents,
  nextTimelineEventIndex,
  timelineEventsForPoint,
  type MapPoint,
  type TimelineEvent,
} from "@/core/map/types";

const points: MapPoint[] = [
  {
    id: "garden",
    entityId: "entity-garden",
    name: "严家花园",
    entityType: "garden",
    lon: 120.5044,
    lat: 31.2547,
    confidence: "exact",
    basis: "OpenStreetMap current feature",
    geometryType: "point",
    uncertaintyRadiusMeters: null,
    areaCoordinates: [],
    extentSource: null,
    extentBasis: null,
    coordinateSystem: "WGS84",
    dynasties: ["qing", "modern"],
    heritageStatus: "extant",
    accessStatus: "verify_before_visit",
    summary: "现存园林",
    address: "木渎镇山塘街",
    evidence: [],
    reviewStatus: null,
    releaseId: null,
    recordKind: "reference",
    startYear: 1736,
    endYear: null,
  },
  {
    id: "bridge",
    entityId: "entity-bridge",
    name: "永安桥",
    entityType: "bridge",
    lon: 120.5043,
    lat: 31.254,
    confidence: "approximate",
    basis: "Cross-source correlation",
    geometryType: "uncertainty_radius",
    uncertaintyRadiusMeters: 750,
    areaCoordinates: [],
    extentSource: "confidence_default",
    extentBasis: "Test uncertainty envelope",
    coordinateSystem: "WGS84",
    dynasties: ["ming", "qing", "modern"],
    heritageStatus: "extant",
    accessStatus: "view_only",
    summary: "现存石桥",
    address: "严家花园前",
    evidence: [],
    reviewStatus: null,
    releaseId: null,
    recordKind: "reference",
    startYear: 1497,
    endYear: null,
  },
];

describe("map catalog filters", () => {
  it("combines dynasty, confidence, type and year filters", () => {
    expect(
      filterMapPoints(points, {
        dynasties: ["qing"],
        entityTypes: ["garden"],
        minConfidence: "exact",
        year: 1800,
      }).map((point) => point.id),
    ).toEqual(["garden"]);
  });

  it("keeps unknown-time records only when requested", () => {
    const unknown = { ...points[0]!, id: "unknown", startYear: null };
    expect(filterMapPoints([unknown], { year: 1800 })).toEqual([]);
    expect(
      filterMapPoints([unknown], { year: 1800, includeUnknownTime: true }),
    ).toHaveLength(1);
  });

  it("separates reviewed references from corpus drafts", () => {
    const draft = {
      ...points[0]!,
      id: "draft",
      recordKind: "corpus" as const,
      reviewStatus: "pending" as const,
      releaseId: "release-working",
    };

    expect(
      filterMapPoints([points[0]!, draft], { recordScopes: ["formal"] }).map(
        (point) => point.id,
      ),
    ).toEqual(["garden"]);
    expect(
      filterMapPoints([points[0]!, draft], { recordScopes: ["draft"] }).map(
        (point) => point.id,
      ),
    ).toEqual(["draft"]);
  });
});

describe("timeline filters", () => {
  const events: TimelineEvent[] = [
    {
      id: "built",
      title: "建桥",
      yearStart: 1497,
      yearEnd: 1497,
      timeLabel: "明弘治十年（1497）",
      precision: "exact",
      pointId: "bridge",
      summary: "建成",
      evidence: [],
      reviewStatus: null,
      releaseId: null,
      recordKind: "reference",
      featured: true,
      importance: "landmark",
    },
  ];

  it("returns events active at the selected year", () => {
    expect(filterTimelineEvents(events, 1497)).toHaveLength(1);
    expect(filterTimelineEvents(events, 1498)).toHaveLength(0);
  });

  it("returns one point's events in chronological order", () => {
    const eventsAtPoint: TimelineEvent[] = [
      {
        ...events[0]!,
        id: "unknown",
        title: "待考事件",
        yearStart: null,
        yearEnd: null,
      },
      { ...events[0]!, id: "later", title: "重修", yearStart: 1600 },
      { ...events[0]!, id: "other", pointId: "garden" },
      events[0]!,
    ];

    expect(
      timelineEventsForPoint(eventsAtPoint, "bridge").map((event) => event.id),
    ).toEqual(["built", "later", "unknown"]);
  });

  it("builds a stable featured-event sequence and cycles playback", () => {
    const sequence = featuredTimelineEvents([
      { ...events[0]!, id: "context", featured: false, yearStart: 1200 },
      { ...events[0]!, id: "same-year-b", yearStart: 1689 },
      { ...events[0]!, id: "unknown", yearStart: null },
      { ...events[0]!, id: "same-year-a", yearStart: 1689 },
      events[0]!,
    ]);

    expect(sequence.map((event) => event.id)).toEqual([
      "built",
      "same-year-a",
      "same-year-b",
    ]);
    expect(nextTimelineEventIndex(sequence, "built")).toBe(1);
    expect(nextTimelineEventIndex(sequence, "same-year-b")).toBe(0);
    expect(nextTimelineEventIndex(sequence, null)).toBe(0);
  });
});
