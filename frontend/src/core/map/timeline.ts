export type TimelineEventLike = {
  id: string;
  title: string;
  yearStart: number | null;
  yearEnd: number | null;
};

export type TimelineScale = {
  startYear: number;
  endYear: number;
  span: number;
};

export type TimelineEventGroup<T extends TimelineEventLike> = {
  id: string;
  year: number;
  events: T[];
  leftPx: number;
  lane: number;
};

export type TimelineTick = {
  year: number;
  position: number;
  leftPx: number;
};

export type TimelineDynastyBand = {
  id: string;
  label: string;
  startYear: number;
  endYear: number;
  leftPx: number;
  widthPx: number;
  track: number;
};

export type TimelineLayout<T extends TimelineEventLike> = {
  scale: TimelineScale | null;
  widthPx: number;
  heightPx: number;
  paddingPx: number;
  laneCount: number;
  groups: TimelineEventGroup<T>[];
  /** @deprecated Use groups. Kept as a small compatibility bridge for callers. */
  items: TimelineEventGroup<T>[];
  ticks: TimelineTick[];
  dynastyBands: TimelineDynastyBand[];
  dynastyBandTrackCount: number;
  eventTopPx: number;
};

const NICE_STEPS = [1, 2, 5, 10];
const DYNASTIES = [
  { id: "tang", label: "唐", startYear: 618, endYear: 907 },
  { id: "song", label: "宋", startYear: 960, endYear: 1279 },
  { id: "yuan", label: "元", startYear: 1271, endYear: 1368 },
  { id: "ming", label: "明", startYear: 1368, endYear: 1644 },
  { id: "qing", label: "清", startYear: 1644, endYear: 1912 },
] as const;

function datedEvents<T extends TimelineEventLike>(events: T[]) {
  return events
    .filter(
      (event): event is T & { yearStart: number } => event.yearStart !== null,
    )
    .sort(
      (left, right) =>
        left.yearStart - right.yearStart ||
        left.id.localeCompare(right.id, "zh-CN"),
    );
}

function tickStep(span: number): number {
  const raw = Math.max(1, span / 10);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  const nice = NICE_STEPS.find((step) => normalized <= step) ?? 10;
  return nice * magnitude;
}

export function buildTimelineScale(
  events: TimelineEventLike[],
): TimelineScale {
  const dated = datedEvents(events);
  if (!dated.length) return { startYear: 0, endYear: 1, span: 1 };
  const minimum = dated[0]!.yearStart;
  const maximum = dated.reduce(
    (latest, event) => Math.max(latest, event.yearEnd ?? event.yearStart),
    minimum,
  );
  const rawSpan = Math.max(1, maximum - minimum);
  const step = tickStep(rawSpan);
  const padding = Math.max(10, Math.ceil(rawSpan * 0.04));
  const startYear = Math.floor((minimum - padding) / step) * step;
  const endYear = Math.ceil((maximum + padding) / step) * step;
  const boundedEndYear = Math.max(startYear + step, endYear);
  return {
    startYear,
    endYear: boundedEndYear,
    span: Math.max(1, boundedEndYear - startYear),
  };
}

export function timelinePosition(year: number, scale: TimelineScale): number {
  if (scale.endYear === scale.startYear) return 0;
  return Math.min(1, Math.max(0, (year - scale.startYear) / scale.span));
}

function buildTicks(
  scale: TimelineScale,
  usableWidthPx: number,
  paddingPx: number,
): TimelineTick[] {
  const step = tickStep(scale.span);
  const first = Math.ceil(scale.startYear / step) * step;
  const ticks: TimelineTick[] = [];
  for (let year = first; year <= scale.endYear; year += step) {
    const position = timelinePosition(year, scale);
    ticks.push({
      year,
      position,
      leftPx: paddingPx + position * usableWidthPx,
    });
  }
  if (ticks[0]?.year !== scale.startYear) {
    ticks.unshift({ year: scale.startYear, position: 0, leftPx: paddingPx });
  }
  if (ticks.at(-1)?.year !== scale.endYear) {
    ticks.push({
      year: scale.endYear,
      position: 1,
      leftPx: paddingPx + usableWidthPx,
    });
  }
  return ticks;
}

function buildDynastyBands(
  scale: TimelineScale,
  usableWidthPx: number,
  paddingPx: number,
): { bands: TimelineDynastyBand[]; trackCount: number } {
  const trackEnds: number[] = [];
  const bands = DYNASTIES.flatMap((dynasty) => {
    const start = Math.max(scale.startYear, dynasty.startYear);
    const end = Math.min(scale.endYear, dynasty.endYear);
    if (end <= start) return [];
    let track = trackEnds.findIndex((trackEnd) => start >= trackEnd);
    if (track < 0) track = trackEnds.length;
    trackEnds[track] = end;
    const leftPx = paddingPx + timelinePosition(start, scale) * usableWidthPx;
    const rightPx = paddingPx + timelinePosition(end, scale) * usableWidthPx;
    return [{
      ...dynasty,
      leftPx,
      widthPx: Math.max(1, rightPx - leftPx),
      track,
    }];
  });
  return { bands, trackCount: Math.max(1, trackEnds.length) };
}

function groupDatedEvents<T extends TimelineEventLike>(events: T[]) {
  const groups = new Map<number, T[]>();
  for (const event of datedEvents(events)) {
    const year = event.yearStart;
    groups.set(year, [...(groups.get(year) ?? []), event]);
  }
  return [...groups.entries()].map(([year, groupedEvents]) => ({
    year,
    events: groupedEvents,
  }));
}

export function buildTimelineLayout<T extends TimelineEventLike>(
  events: T[],
  options: {
    minWidth?: number;
    pixelsPerYear?: number;
    itemWidth?: number;
    laneGap?: number;
    laneHeight?: number;
  } = {},
): TimelineLayout<T> {
  const dated = datedEvents(events);
  if (!dated.length) {
    return {
      scale: null,
      widthPx: options.minWidth ?? 960,
      heightPx: 1,
      paddingPx: 0,
      laneCount: 0,
      groups: [],
      items: [],
      ticks: [],
      dynastyBands: [],
      dynastyBandTrackCount: 0,
      eventTopPx: 80,
    };
  }
  const scale = buildTimelineScale(events);
  const itemWidth = options.itemWidth ?? 136;
  const paddingPx = itemWidth / 2 + 18;
  const usableWidthPx = Math.max(
    options.minWidth ?? 960,
    scale.span * (options.pixelsPerYear ?? 0.75),
  );
  const widthPx = usableWidthPx + paddingPx * 2;
  const laneGap = options.laneGap ?? 18;
  const laneHeight = options.laneHeight ?? 104;
  const dynastyBandLayout = buildDynastyBands(scale, usableWidthPx, paddingPx);
  const eventTopPx = 88 + (dynastyBandLayout.trackCount - 1) * 22;
  const laneEnds: number[] = [];
  const groups = groupDatedEvents(events).map(({ year, events: groupedEvents }) => {
    const leftPx = paddingPx + timelinePosition(year, scale) * usableWidthPx;
    const intervalStart = leftPx - itemWidth / 2;
    const intervalEnd = leftPx + itemWidth / 2;
    let lane = laneEnds.findIndex((end) => intervalStart >= end + laneGap);
    if (lane < 0) {
      // Dense data stays within two compact tracks; this fallback preserves
      // the true x coordinate when both tracks are occupied.
      lane = laneEnds.length < 2
        ? laneEnds.length
        : laneEnds.indexOf(Math.min(...laneEnds));
    }
    laneEnds[lane] = intervalEnd;
    return {
      id: `timeline-year-${year}`,
      year,
      events: groupedEvents,
      leftPx,
      lane,
    };
  });
  const laneCount = Math.min(2, Math.max(1, laneEnds.length));
  return {
    scale,
    widthPx,
    heightPx: Math.max(
      260,
      Math.min(340, eventTopPx + Math.min(2, laneCount) * laneHeight + 24),
    ),
    paddingPx,
    laneCount,
    groups,
    items: groups,
    ticks: buildTicks(scale, usableWidthPx, paddingPx),
    dynastyBands: dynastyBandLayout.bands,
    dynastyBandTrackCount: dynastyBandLayout.trackCount,
    eventTopPx,
  };
}
