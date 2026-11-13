import { useMemo, useState } from "react";

import {
  buildStudyRoute,
  type MapCatalog,
  type MapPoint,
  type MapRoute,
} from "@/core/map/types";

const EXAMPLE_ROUTE_ID = "example-mudu-humanities-half-day";
// Editorial itinerary only. Coordinates, provenance and confidence come from
// the loaded points; names must never be used to match historical/corpus rows.
const EXAMPLE_STOPS = [
  ["pt-yongan-bridge", "entity-bridge-yongan"],
  ["pt-mingyue-temple", "entity-temple-mingyue"],
  ["pt-hongyin", "entity-garden-hongyin"],
  ["pt-gusong-garden", "entity-garden-gusong"],
] as const;

function exampleRoute(points: MapPoint[]): MapRoute {
  const stops = EXAMPLE_STOPS.flatMap(([id, entityId]) => {
    const point = points.find(
      (item) =>
        item.id === id &&
        item.entityId === entityId &&
        item.recordKind === "reference" &&
        !item.releaseId,
    );
    return point ? [point] : [];
  });
  return {
    id: EXAMPLE_ROUTE_ID,
    name: "木渎古镇人文半日研学（示例）",
    duration: "half_day",
    audience: "学生与文化爱好者",
    summary:
      "以永安桥、明月古寺、虹饮山房和古松园为观察节点，串联桥梁、寺院与园林文化。可按活动需要添加、移除站点并调整顺序。",
    stopIds: stops.map((point) => point.id),
    disclaimer:
      "示例仅为研学内容编排建议，半日为活动安排参考。连线表示站点顺序，不是道路导航；票务、开放时间、宗教场所规则与现场可达性需出发前核验。永安桥为近似定位，请以点位详情为准。",
    evidence: [
      ...new Map(
        stops.flatMap((point) =>
          point.evidence.map((item) => [item.id, item] as const),
        ),
      ).values(),
    ],
  };
}

type RouteDraft = { routeId: string; stopIds: string[] };

export function useStudyRoutes(catalog: MapCatalog | null) {
  const routes = useMemo(
    () =>
      catalog
        ? catalog.routes.length
          ? catalog.routes
          : [exampleRoute(catalog.points)]
        : [],
    [catalog],
  );
  const [draft, setDraft] = useState<RouteDraft | null>(null);
  const activeRoute =
    routes.find((route) => route.id === draft?.routeId) ?? routes[0] ?? null;
  const routeStops = useMemo(
    () =>
      buildStudyRoute(catalog?.points ?? [], {
        stopIds:
          draft && draft.routeId === activeRoute?.id
            ? draft.stopIds
            : (activeRoute?.stopIds ?? []),
      }),
    [catalog, activeRoute, draft],
  );
  const availableStops = useMemo(() => {
    const included = new Set(routeStops.map((point) => point.id));
    return (catalog?.points ?? []).filter((point) => !included.has(point.id));
  }, [catalog, routeStops]);

  const updateStops = (update: (ids: string[]) => string[]) => {
    if (!activeRoute) return;
    setDraft((current) => ({
      routeId: activeRoute.id,
      stopIds: update(
        buildStudyRoute(
          catalog?.points ?? [],
          current?.routeId === activeRoute.id ? current : activeRoute,
        ).map((point) => point.id),
      ),
    }));
  };
  const selectRoute = (id: string) => {
    const route = routes.find((item) => item.id === id);
    if (route) setDraft({ routeId: route.id, stopIds: [...route.stopIds] });
  };

  return {
    routes,
    activeRoute,
    isExample: activeRoute?.id === EXAMPLE_ROUTE_ID,
    routeStops,
    availableStops,
    selectRoute,
    resetRoute: () => activeRoute && selectRoute(activeRoute.id),
    addStop: (id: string) => {
      if (!catalog?.points.some((point) => point.id === id)) return;
      updateStops((ids) => (ids.includes(id) ? ids : [...ids, id]));
    },
    removeStop: (id: string) =>
      updateStops((ids) => ids.filter((item) => item !== id)),
    moveStop: (id: string, direction: -1 | 1) =>
      updateStops((ids) => {
        const index = ids.indexOf(id);
        const nextIndex = index + direction;
        if (index < 0 || nextIndex < 0 || nextIndex >= ids.length) return ids;
        const next = [...ids];
        [next[index], next[nextIndex]] = [next[nextIndex]!, next[index]!];
        return next;
      }),
  };
}
