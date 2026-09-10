import { describe, expect, it } from "@rstest/core";

import {
  buildTimelineLayout,
  buildTimelineScale,
  timelinePosition,
} from "@/core/map/timeline";

const events = [
  {
    id: "jin",
    title: "东晋建寺",
    yearStart: 317,
    yearEnd: 420,
  },
  {
    id: "song",
    title: "宋代修葺",
    yearStart: 1034,
    yearEnd: 1034,
  },
  {
    id: "ming",
    title: "明代建桥",
    yearStart: 1497,
    yearEnd: 1497,
  },
  {
    id: "qing-a",
    title: "清代事件甲",
    yearStart: 1689,
    yearEnd: 1689,
  },
  {
    id: "qing-b",
    title: "清代事件乙",
    yearStart: 1689,
    yearEnd: 1689,
  },
];

describe("historical timeline scale", () => {
  it("positions events by their year rather than their array index", () => {
    const scale = buildTimelineScale(events);

    expect(scale.startYear).toBe(317);
    expect(scale.endYear).toBe(1689);
    expect(timelinePosition(1497, scale)).toBeCloseTo(
      (1497 - 317) / (1689 - 317),
      5,
    );
    expect(timelinePosition(1497, scale)).toBeGreaterThan(
      timelinePosition(1034, scale),
    );
  });

  it("assigns same-year events to separate lanes", () => {
    const layout = buildTimelineLayout(events, {
      minWidth: 960,
      itemWidth: 156,
      laneGap: 12,
    });
    const sameYear = layout.items.filter(
      (item) => item.event.yearStart === 1689,
    );

    expect(sameYear).toHaveLength(2);
    expect(sameYear[0]?.lane).not.toBe(sameYear[1]?.lane);
    expect(layout.laneCount).toBeGreaterThanOrEqual(2);
    expect(layout.widthPx).toBeGreaterThanOrEqual(960);
  });

  it("creates readable historical ticks across the whole domain", () => {
    const layout = buildTimelineLayout(events);
    const years = layout.ticks.map((tick) => tick.year);

    expect(years[0]).toBeGreaterThanOrEqual(317);
    expect(years.at(-1)).toBeLessThanOrEqual(1689);
    expect(
      new Set(years.slice(1).map((year, index) => year - years[index]!)).size,
    ).toBe(1);
  });
});
