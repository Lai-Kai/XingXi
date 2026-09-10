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

export type TimelineLayoutItem<T extends TimelineEventLike> = {
  event: T;
  leftPx: number;
  lane: number;
};

export type TimelineTick = {
  year: number;
  position: number;
  leftPx: number;
};

export type TimelineLayout<T extends TimelineEventLike> = {
  scale: TimelineScale | null;
  widthPx: number;
  heightPx: number;
  paddingPx: number;
  laneCount: number;
  items: TimelineLayoutItem<T>[];
  ticks: TimelineTick[];
};

const NICE_STEPS = [1, 2, 5, 10];

function knownEvents<T extends TimelineEventLike>(events: T[]) {
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

export function buildTimelineScale(events: TimelineEventLike[]): TimelineScale {
  const dated = knownEvents(events);
  const startYear = dated[0]?.yearStart ?? 0;
  const endYear = dated.reduce(
    (latest, event) => Math.max(latest, event.yearEnd ?? event.yearStart),
    startYear,
  );
  return {
    startYear,
    endYear,
    span: Math.max(1, endYear - startYear),
  };
}

export function timelinePosition(year: number, scale: TimelineScale): number {
  if (scale.endYear === scale.startYear) return 0;
  return Math.min(1, Math.max(0, (year - scale.startYear) / scale.span));
}

function tickStep(span: number): number {
  const raw = Math.max(1, span / 10);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  const nice = NICE_STEPS.find((step) => normalized <= step) ?? 10;
  return nice * magnitude;
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
  if (ticks.length === 0) {
    ticks.push({ year: scale.startYear, position: 0, leftPx: paddingPx });
  }
  return ticks;
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
  const scale = buildTimelineScale(events);
  const dated = knownEvents(events);
  const itemWidth = options.itemWidth ?? 156;
  const paddingPx = itemWidth / 2 + 18;
  const usableWidthPx = Math.max(
    options.minWidth ?? 960,
    scale.span * (options.pixelsPerYear ?? 0.65),
  );
  const widthPx = usableWidthPx + paddingPx * 2;
  const laneGap = options.laneGap ?? 12;
  const laneHeight = options.laneHeight ?? 68;
  const laneEnds: number[] = [];
  const items = dated.map((event) => {
    const leftPx =
      paddingPx + timelinePosition(event.yearStart, scale) * usableWidthPx;
    const intervalStart = leftPx - itemWidth / 2;
    const intervalEnd = leftPx + itemWidth / 2;
    let lane = laneEnds.findIndex((end) => intervalStart >= end + laneGap);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = intervalEnd;
    return { event, leftPx, lane };
  });

  return {
    scale,
    widthPx,
    heightPx: Math.max(1, laneEnds.length) * laneHeight,
    paddingPx,
    laneCount: Math.max(1, laneEnds.length),
    items,
    ticks: buildTicks(scale, usableWidthPx, paddingPx),
  };
}
