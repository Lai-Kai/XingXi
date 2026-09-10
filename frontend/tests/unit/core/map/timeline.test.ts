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

    expect(scale.startYear).toBeLessThan(317);
    expect(scale.endYear).toBeGreaterThan(1689);
    expect(timelinePosition(1497, scale)).toBeCloseTo(
      (1497 - scale.startYear) / scale.span,
      5,
    );
    expect(timelinePosition(1497, scale)).toBeGreaterThan(
      timelinePosition(1034, scale),
    );
  });

  it("groups same-year events into one compact timeline node", () => {
    const layout = buildTimelineLayout(events, {
      minWidth: 960,
      itemWidth: 156,
      laneGap: 12,
    });
    const sameYear = layout.groups.filter(
      (item) => item.year === 1689,
    );

    expect(sameYear).toHaveLength(1);
    expect(sameYear[0]?.events).toHaveLength(2);
    expect(layout.heightPx).toBeLessThanOrEqual(340);
    expect(layout.widthPx).toBeGreaterThanOrEqual(960);
  });

  it("creates readable historical ticks across the whole domain", () => {
    const layout = buildTimelineLayout(events);
    const years = layout.ticks.map((tick) => tick.year);

    expect(years[0]).toBeLessThanOrEqual(317);
    expect(years.at(-1)).toBeGreaterThanOrEqual(1689);
    expect(
      new Set(years.slice(1).map((year, index) => year - years[index]!)).size,
    ).toBe(1);
  });

  it("uses the same coordinate system for ticks and dynasty bands", () => {
    const layout = buildTimelineLayout(events);
    const song = layout.dynastyBands.find((band) => band.id === "song");
    const songTick = layout.ticks.find((tick) => tick.year === 1000);

    expect(song).toBeDefined();
    expect(songTick).toBeDefined();
    expect(song!.leftPx).toBeLessThan(songTick!.leftPx);
    expect(song!.leftPx + song!.widthPx).toBeGreaterThan(songTick!.leftPx);
    expect(song!.widthPx).toBeGreaterThan(0);
  });

  it("keeps overlapping dynasty ranges on separate compact bands", () => {
    const layout = buildTimelineLayout(events);
    const song = layout.dynastyBands.find((band) => band.id === "song");
    const yuan = layout.dynastyBands.find((band) => band.id === "yuan");

    expect(song).toBeDefined();
    expect(yuan).toBeDefined();
    expect(song!.track).not.toBe(yuan!.track);
    expect(layout.eventTopPx).toBeGreaterThan(80);
  });
});
