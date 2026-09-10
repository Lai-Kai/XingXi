"use client";

import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BookOpen,
  CalendarRange,
  ChevronDown,
  ChevronUp,
  Compass,
  Download,
  ExternalLink,
  Filter,
  FilterX,
  ImageOff,
  Info,
  Layers3,
  LocateFixed,
  Map as MapIcon,
  Network,
  Pause,
  Play,
  Route as RouteIcon,
  Send,
  Quote,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  BusinessErrorState,
  BusinessLoadingState,
} from "@/components/workspace/business-page";
import { GlbViewerSlot } from "@/components/workspace/map/glb-viewer-slot";
import { MapLibreCanvas } from "@/components/workspace/map/maplibre-canvas";
import { fetchMapCatalog, planMapRoute } from "@/core/map/api";
import {
  defaultMapLayerOpacity,
  getRenderableMapLayers,
} from "@/core/map/layers";
import { buildTimelineLayout } from "@/core/map/timeline";
import {
  buildStudyRoute,
  filterMapPoints,
  nextTimelineEventIndex,
  type DynastyLayer,
  type MapCatalog,
  type MapEvidence,
  type MapRelation,
  type MapPoint,
  type MapRecordScope,
  type PlannedMapRoute,
  type SpatialConfidence,
  type TimelineEvent,
  type UserMapLocation,
} from "@/core/map/types";
import { recordOperationEvent } from "@/core/operations/api";
import { xingxiChatHref } from "@/core/threads/xingxi-entry";
import { cn } from "@/lib/utils";

const dynastyLabels: Record<DynastyLayer, string> = {
  spring_autumn: "春秋",
  jin: "晋",
  liang: "南梁",
  tang: "唐",
  song: "宋",
  ming: "明",
  qing: "清",
  modern: "近现代",
};
const entityTypeLabels: Record<string, string> = {
  historic_district: "历史街区",
  garden: "园林",
  bridge: "桥梁",
  temple: "寺庙",
  residence: "宅第",
  landform: "山水地貌",
};
const confidenceLabels: Record<SpatialConfidence, string> = {
  exact: "现状精确",
  approximate: "近似定位",
  speculative: "推测定位",
};
const extentSourceLabels: Record<
  NonNullable<MapPoint["extentSource"]>,
  string
> = {
  evidence: "资料出处",
  historical_map: "历史地图",
  editorial_estimate: "编辑估计",
  confidence_default: "按置信等级生成",
};

function spatialRepresentationLabel(point: MapPoint) {
  if (point.geometryType === "historical_area") return "史料边界范围";
  if (point.geometryType === "uncertainty_radius") {
    return `约 ${point.uncertaintyRadiusMeters?.toLocaleString("zh-CN") ?? "未知"} 米的不确定范围`;
  }
  return "精确点";
}
const accessLabels: Record<MapPoint["accessStatus"], string> = {
  public_space: "公共空间",
  ticket_or_hours: "需核验票务与开放时间",
  religious_site: "宗教场所，遵守参访规则",
  view_only: "建议外部观察",
  verify_before_visit: "出发前核验",
};
const reviewLabels = {
  pending: "待复核语料草稿",
  reviewed: "已复核",
  disputed: "存在争议",
  rejected: "已驳回",
} as const;

function mapRecordScope(record: {
  recordKind: "reference" | "corpus";
  reviewStatus: MapPoint["reviewStatus"];
}): MapRecordScope {
  return record.recordKind === "corpus" && record.reviewStatus !== "reviewed"
    ? "draft"
    : "formal";
}

type MapMode = "explore" | "route";
type MapToolPanel = "filters" | "layers" | "route";

const relationLabels: Record<string, string> = {
  located_in: "位于",
  built_by: "由其营建",
  repaired_in: "于此修缮",
  crosses: "跨越",
  related_to: "关联",
  sibling_of: "同源",
  spouse_of: "配偶",
  parent_of: "亲属",
  lived_in: "居住于",
  visited: "到访",
  born_in: "出生于",
  worked_at: "任职于",
  studied_at: "求学于",
  died_at: "卒于",
  composed_at: "赋诗于",
  mentioned_in_poetry: "诗文提及",
  documented_in: "见于",
};

function relationLabel(relationType: string) {
  return relationLabels[relationType] ?? relationType;
}

function relationSentence(relation: MapRelation) {
  switch (relation.relationType) {
    case "built_by":
      return `${relation.subjectName}由${relation.objectName}营建`;
    case "repaired_in":
      return `${relation.subjectName}于${relation.objectName}修缮`;
    case "visited":
      return `${relation.subjectName}到访${relation.objectName}`;
    case "born_in":
      return `${relation.subjectName}出生于${relation.objectName}`;
    case "died_at":
      return `${relation.subjectName}卒于${relation.objectName}`;
    case "composed_at":
      return `${relation.subjectName}赋诗于${relation.objectName}`;
    case "located_in":
      return `${relation.subjectName}位于${relation.objectName}`;
    case "worked_at":
      return `${relation.subjectName}任职于${relation.objectName}`;
    case "studied_at":
      return `${relation.subjectName}求学于${relation.objectName}`;
    case "lived_in":
      return `${relation.subjectName}居住于${relation.objectName}`;
    case "mentioned_in_poetry":
      return `${relation.objectName}诗文提及${relation.subjectName}`;
    default:
      return `${relation.subjectName}${relationLabel(relation.relationType)}${relation.objectName}`;
  }
}

function evidenceDateLabel(source: MapEvidence) {
  return `${source.publisher} · 读取于 ${source.retrievedAt}`;
}

function EvidenceTrail({
  sources,
  compact = false,
}: {
  sources: MapEvidence[];
  compact?: boolean;
}) {
  const hasMedia = sources.some((source) => (source.media?.length ?? 0) > 0);
  return (
    <div className={cn("space-y-2", compact && "space-y-1.5")}>
      {sources.length ? (
        sources.map((source) => (
          <div
            key={source.id}
            className={cn(
              "text-xs leading-5",
              compact ? "text-[#66544c]" : "text-[#5e4b43]",
            )}
          >
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-medium text-[#276b75] hover:underline"
            >
              {source.title} <ExternalLink className="size-3" />
            </a>
            <div className="text-muted-foreground">
              {evidenceDateLabel(source)}
            </div>
            {source.quote && (
              <blockquote className="mt-1 border-l-2 border-[#cba995] pl-2 text-[#72564a]">
                <Quote className="mr-1 inline size-3" />“{source.quote}”
              </blockquote>
            )}
            {(source.media ?? []).map((media) => (
              <a
                key={`${source.id}-${media.url}`}
                href={media.url}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-[#276b75] underline underline-offset-2"
              >
                {media.caption} <ExternalLink className="size-3" />
              </a>
            ))}
          </div>
        ))
      ) : (
        <p className="text-muted-foreground text-xs">
          当前记录暂无可核验来源。
        </p>
      )}
      {!hasMedia && (
        <p
          data-map-media-status="unavailable"
          className="flex items-center gap-1.5 border-t border-dashed border-[#ead8cd] pt-2 text-[11px] leading-4 text-[#8b7467]"
        >
          <ImageOff className="size-3.5 shrink-0" />
          暂无授权影像、碑刻拓本或三维模型
        </p>
      )}
    </div>
  );
}

function PointDetails({
  point,
  events,
  relations,
  dataNotice,
  onClose,
}: {
  point: MapPoint;
  events: TimelineEvent[];
  relations: MapRelation[];
  dataNotice: string;
  onClose?: () => void;
}) {
  const pointEvents = events
    .filter((event) => event.pointId === point.id)
    .sort(
      (left, right) =>
        (left.yearStart ?? Number.MAX_SAFE_INTEGER) -
        (right.yearStart ?? Number.MAX_SAFE_INTEGER),
    );
  const pointRelations = relations.filter(
    (relation) =>
      relation.subjectId === point.entityId ||
      relation.objectId === point.entityId,
  );

  return (
    <section aria-label="点位详情" className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-start justify-between gap-3 border-b py-4 pr-14 pl-5">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-semibold">{point.name}</h2>
          <span
            className={cn(
              "mt-1.5 inline-flex rounded px-2 py-1 text-xs",
              point.confidence === "exact" && "bg-emerald-50 text-emerald-800",
              point.confidence === "approximate" &&
                "bg-amber-50 text-amber-800",
              point.confidence === "speculative" && "bg-rose-50 text-rose-800",
            )}
          >
            {confidenceLabels[point.confidence]}
          </span>
          {point.reviewStatus && (
            <span
              className={cn(
                "mt-1.5 ml-1.5 inline-flex rounded px-2 py-1 text-xs",
                point.reviewStatus === "reviewed"
                  ? "bg-emerald-50 text-emerald-800"
                  : "bg-amber-50 text-amber-900",
              )}
            >
              {reviewLabels[point.reviewStatus]}
            </span>
          )}
        </div>
        {onClose && (
          <button
            type="button"
            aria-label="关闭点位详情"
            title="关闭点位详情"
            onClick={onClose}
            className="grid size-9 shrink-0 place-items-center rounded-md text-[#52686c] hover:bg-[#eef5f4]"
          >
            <X className="size-4" />
          </button>
        )}
      </div>

      <Tabs defaultValue="overview" className="min-h-0 flex-1 gap-0">
        <TabsList
          variant="line"
          aria-label="点位资料"
          className="mx-5 mt-2 w-[calc(100%-2.5rem)] justify-start border-b"
        >
          <TabsTrigger value="overview" className="flex-none px-3">
            概览
          </TabsTrigger>
          <TabsTrigger value="history" className="flex-none px-3">
            沿革
          </TabsTrigger>
          <TabsTrigger value="sources" className="flex-none px-3">
            来源
          </TabsTrigger>
        </TabsList>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <TabsContent value="overview" className="space-y-4">
            <p className="text-muted-foreground text-sm leading-6">
              {point.summary}
            </p>
            <dl className="grid grid-cols-[76px_1fr] gap-y-2 text-sm">
              <dt className="text-muted-foreground">类型</dt>
              <dd>{entityTypeLabels[point.entityType] ?? point.entityType}</dd>
              <dt className="text-muted-foreground">遗存状态</dt>
              <dd>{point.heritageStatus === "extant" ? "现存" : "待核验"}</dd>
              <dt className="text-muted-foreground">参访提示</dt>
              <dd>{accessLabels[point.accessStatus]}</dd>
              <dt className="text-muted-foreground">地址</dt>
              <dd>{point.address}</dd>
              <dt className="text-muted-foreground">
                {point.geometryType === "point" ? "坐标" : "估计中心"}
              </dt>
              <dd className="font-mono text-xs">
                {point.lon.toFixed(6)}, {point.lat.toFixed(6)} · WGS84
              </dd>
              <dt className="text-muted-foreground">空间表达</dt>
              <dd>{spatialRepresentationLabel(point)}</dd>
              {point.extentSource && (
                <>
                  <dt className="text-muted-foreground">范围来源</dt>
                  <dd>{extentSourceLabels[point.extentSource]}</dd>
                </>
              )}
              {point.releaseId && (
                <>
                  <dt className="text-muted-foreground">知识版本</dt>
                  <dd className="font-mono text-xs break-all">
                    {point.releaseId}
                  </dd>
                </>
              )}
            </dl>
            <div className="rounded border border-[#e1d5af] bg-[#fffaf0] px-3 py-2 text-xs leading-5 text-[#755f26]">
              <div className="mb-1 flex items-center gap-1.5 font-medium">
                <Info className="size-3.5" /> 定位依据
              </div>
              {point.basis}
            </div>
            {point.extentBasis && (
              <div className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-950">
                <div className="mb-1 flex items-center gap-1.5 font-medium">
                  <AlertTriangle className="size-3.5" /> 范围依据
                </div>
                {point.extentBasis}
              </div>
            )}
            <GlbViewerSlot asset={null} />
            <section aria-label="证据片段" className="border-t pt-3">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-medium">
                <Quote className="size-4" /> 文献证据
              </h3>
              <EvidenceTrail sources={point.evidence} />
            </section>
          </TabsContent>

          <TabsContent value="history">
            {pointEvents.length ? (
              <ol className="space-y-4">
                {pointEvents.map((event) => (
                  <li
                    key={event.id}
                    className="border-l-2 border-[#9ebcba] pl-3"
                  >
                    <div className="text-xs font-medium text-[#276b75]">
                      {event.timeLabel}
                    </div>
                    <div className="mt-1 text-sm font-medium">
                      {event.title}
                    </div>
                    <p className="text-muted-foreground mt-1 text-xs leading-5">
                      {event.summary}
                    </p>
                    <EvidenceTrail sources={event.evidence} compact />
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-muted-foreground text-sm leading-6">
                暂无已登记的沿革事件。
              </p>
            )}
            {pointRelations.length > 0 && (
              <section aria-label="资料关联" className="mt-6 border-t pt-4">
                <h3 className="mb-3 flex items-center gap-2 text-sm font-medium">
                  <Network className="size-4" /> 资料关联
                </h3>
                <ul className="space-y-4">
                  {pointRelations.map((relation) => {
                    return (
                      <li
                        key={relation.id}
                        className="border-l-2 border-[#cba995] pl-3"
                      >
                        <p className="text-sm font-medium">
                          {relationSentence(relation)}
                        </p>
                        <p className="text-muted-foreground mt-1 text-[11px]">
                          关系置信度 {Math.round(relation.confidence * 100)}%
                          {relation.startTime ? ` · ${relation.startTime}` : ""}
                        </p>
                        <div className="mt-2">
                          <EvidenceTrail sources={relation.evidence} compact />
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}
          </TabsContent>

          <TabsContent value="sources">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-medium">
              <BookOpen className="size-4" /> 可核验来源
            </h3>
            <EvidenceTrail sources={point.evidence} />
            {point.evidence.some((source) => source.note) && (
              <div className="mt-3 space-y-1 border-t pt-3">
                {point.evidence.map((source) => (
                  <p
                    key={`${source.id}-note`}
                    className="text-muted-foreground text-xs"
                  >
                    {source.title}：{source.note}
                  </p>
                ))}
              </div>
            )}
            <p className="text-muted-foreground mt-5 border-t pt-3 text-xs leading-5">
              {dataNotice}
            </p>
          </TabsContent>
        </div>
      </Tabs>

      <div className="border-t px-5 py-3">
        <Link
          href={xingxiChatHref(
            `请围绕地图实体“${point.name}”开展考证。先核对地图所列来源，再说明历史沿革、定位可靠程度与可核验出处；资料出处不足的部分明确保留。`,
            "pro",
          )}
          className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-md bg-[#183f42] px-3 text-sm text-white hover:bg-[#28575b]"
        >
          <Send className="size-3.5" /> 让星羲考证
        </Link>
      </div>
    </section>
  );
}

function moveItem(items: string[], index: number, direction: -1 | 1) {
  const nextIndex = index + direction;
  if (nextIndex < 0 || nextIndex >= items.length) return items;
  const next = [...items];
  [next[index], next[nextIndex]] = [next[nextIndex]!, next[index]!];
  return next;
}

function downloadRoute(name: string, stops: MapPoint[], disclaimer: string) {
  const body = [
    `# ${name}`,
    "",
    ...stops.flatMap((stop, index) => [
      `## ${index + 1}. ${stop.name}`,
      stop.summary,
      `- 地址：${stop.address}`,
      `- 定位：${confidenceLabels[stop.confidence]}`,
      `- 参访：${accessLabels[stop.accessStatus]}`,
      `- 来源：${stop.evidence.map((item) => item.url).join("、")}`,
      "",
    ]),
    `> 注意：${disclaimer}`,
  ].join("\n");
  const blob = new Blob([body], { type: "text/markdown;charset=utf-8" });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = `${name}.md`;
  anchor.click();
  URL.revokeObjectURL(href);
}

export default function MapPage() {
  const [catalog, setCatalog] = useState<MapCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [mapMode, setMapMode] = useState<MapMode>("explore");
  const [toolPanel, setToolPanel] = useState<MapToolPanel | null>(null);
  const [detailSheetOpen, setDetailSheetOpen] = useState(false);
  const [compactLayout, setCompactLayout] = useState(false);
  const [timelineExpanded, setTimelineExpanded] = useState(true);
  const [query, setQuery] = useState("");
  const [dynasty, setDynasty] = useState<DynastyLayer | "all">("all");
  const [minConfidence, setMinConfidence] =
    useState<SpatialConfidence>("speculative");
  const [entityType, setEntityType] = useState("all");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [appliedDynasty, setAppliedDynasty] = useState<DynastyLayer | "all">(
    "all",
  );
  const [appliedMinConfidence, setAppliedMinConfidence] =
    useState<SpatialConfidence>("speculative");
  const [appliedEntityType, setAppliedEntityType] = useState("all");
  const [recordScope, setRecordScope] = useState<"all" | MapRecordScope>("all");
  const [appliedRecordScope, setAppliedRecordScope] = useState<
    "all" | MapRecordScope
  >("all");
  const [year, setYear] = useState(317);
  const [includeUnknownTime, setIncludeUnknownTime] = useState(true);
  const [appliedIncludeUnknownTime, setAppliedIncludeUnknownTime] =
    useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [visibleLayerIds, setVisibleLayerIds] = useState<string[] | null>(null);
  const [layerOpacity, setLayerOpacity] = useState<Record<string, number>>({});
  const [activeRouteId, setActiveRouteId] = useState<string | null>(null);
  const [routeStopIds, setRouteStopIds] = useState<string[]>([]);
  const [showTrajectory, setShowTrajectory] = useState(false);
  const [selectedTrajectoryId, setSelectedTrajectoryId] = useState<
    string | null
  >(null);
  const [playing, setPlaying] = useState(false);
  const [activeEventId, setActiveEventId] = useState<string | null>(null);
  const [storyCardOpen, setStoryCardOpen] = useState(true);
  const timelineScrollRef = useRef<HTMLDivElement | null>(null);
  const timelineEventRefs = useRef(new Map<string, HTMLButtonElement>());
  const [userLocation, setUserLocation] = useState<UserMapLocation | null>(
    null,
  );
  const locationWatchIdRef = useRef<number | null>(null);
  const [locationTracking, setLocationTracking] = useState(false);
  const [locationFocusToken, setLocationFocusToken] = useState(0);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [plannedRoute, setPlannedRoute] = useState<PlannedMapRoute | null>(
    null,
  );
  const [locating, setLocating] = useState(false);
  const [routePlanning, setRoutePlanning] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);

  const selectPoint = useCallback(
    (pointId: string) => {
      setSelectedId(pointId);
      setToolPanel(null);
      if (compactLayout) setDetailSheetOpen(true);
      const point = catalog?.points.find((item) => item.id === pointId);
      recordOperationEvent({
        event_type: "map_point_click",
        entity_id: point?.entityId ?? pointId,
        entity_name: point?.name,
        metadata: { point_id: pointId },
      });
    },
    [catalog, compactLayout],
  );

  useEffect(() => {
    const media = window.matchMedia("(max-width: 1279px)");
    const updateLayout = () => setCompactLayout(media.matches);
    updateLayout();
    media.addEventListener("change", updateLayout);
    return () => media.removeEventListener("change", updateLayout);
  }, []);

  useEffect(() => {
    if (!compactLayout) setDetailSheetOpen(false);
  }, [compactLayout]);

  useEffect(
    () => () => {
      if (locationWatchIdRef.current !== null && navigator.geolocation) {
        navigator.geolocation.clearWatch(locationWatchIdRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    fetchMapCatalog(controller.signal)
      .then((nextCatalog) => {
        setCatalog(nextCatalog);
        const firstRoute = nextCatalog.routes[0];
        setActiveRouteId((current) => current ?? firstRoute?.id ?? null);
        setRouteStopIds((current) =>
          current.length ? current : (firstRoute?.stopIds ?? []),
        );
        setSelectedTrajectoryId(
          (current) => current ?? nextCatalog.trajectories[0]?.id ?? null,
        );
        const renderableLayers = getRenderableMapLayers(nextCatalog.layers);
        setVisibleLayerIds(renderableLayers.map((layer) => layer.id));
        setLayerOpacity(
          Object.fromEntries(
            renderableLayers.map((layer) => [
              layer.id,
              defaultMapLayerOpacity(layer),
            ]),
          ),
        );
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "无法读取地图资料");
      });
    return () => controller.abort();
  }, [reloadKey]);

  const points = useMemo(
    () =>
      filterMapPoints(catalog?.points ?? [], {
        query: appliedQuery,
        dynasties: appliedDynasty === "all" ? undefined : [appliedDynasty],
        minConfidence: appliedMinConfidence,
        entityTypes:
          appliedEntityType === "all" ? undefined : [appliedEntityType],
        year,
        includeUnknownTime: appliedIncludeUnknownTime,
        recordScopes:
          appliedRecordScope === "all" ? undefined : [appliedRecordScope],
      }),
    [
      appliedDynasty,
      appliedEntityType,
      appliedIncludeUnknownTime,
      appliedMinConfidence,
      appliedQuery,
      appliedRecordScope,
      catalog,
      year,
    ],
  );
  const selected = points.find((point) => point.id === selectedId) ?? null;
  const activeRoute =
    catalog?.routes.find((route) => route.id === activeRouteId) ?? null;
  const routeStops = useMemo(
    () => buildStudyRoute(catalog?.points ?? [], { stopIds: routeStopIds }),
    [catalog, routeStopIds],
  );
  const trajectory =
    catalog?.trajectories.find((item) => item.id === selectedTrajectoryId) ??
    catalog?.trajectories[0] ??
    null;
  const trajectoryPoints = useMemo(() => {
    if (!showTrajectory || !trajectory || !catalog) return [];
    const visiblePointIds = new Set(points.map((point) => point.id));
    const byId = new Map(catalog.points.map((point) => [point.id, point]));
    return trajectory.points
      .filter(
        (point) =>
          visiblePointIds.has(point.pointId) &&
          (point.yearStart === null || point.yearStart <= year),
      )
      .map((point) => byId.get(point.pointId))
      .filter((point): point is MapPoint => Boolean(point));
  }, [catalog, points, showTrajectory, trajectory, year]);
  const enabledMapLayerIds = useMemo(
    () =>
      visibleLayerIds ??
      getRenderableMapLayers(catalog?.layers ?? []).map((layer) => layer.id),
    [catalog?.layers, visibleLayerIds],
  );
  const timelineEvents = useMemo(() => {
    const rows = (catalog?.events ?? []).filter(
      (event) =>
        appliedRecordScope === "all" ||
        mapRecordScope(event) === appliedRecordScope,
    );
    return [...rows].sort((left, right) => {
      if (left.yearStart === null) return 1;
      if (right.yearStart === null) return -1;
      return (
        left.yearStart - right.yearStart ||
        left.id.localeCompare(right.id, "zh-CN")
      );
    });
  }, [appliedRecordScope, catalog]);
  const timelineLayout = useMemo(
    () => buildTimelineLayout(timelineEvents),
    [timelineEvents],
  );
  const undatedTimelineEvents = useMemo(
    () => timelineEvents.filter((event) => event.yearStart === null),
    [timelineEvents],
  );
  const activeEvent =
    timelineEvents.find((event) => event.id === activeEventId) ?? null;
  const activePoint = activeEvent
    ? (catalog?.points.find((point) => point.id === activeEvent.pointId) ??
      null)
    : null;
  const activePointEvents = activePoint
    ? timelineEvents.filter((event) => event.pointId === activePoint.id)
    : [];
  const activePointRelations = activePoint
    ? (catalog?.relations.filter(
        (relation) =>
          relation.subjectId === activePoint.entityId ||
          relation.objectId === activePoint.entityId,
      ) ?? [])
    : [];

  const activateTimelineEvent = useCallback((event: TimelineEvent) => {
    setActiveEventId(event.id);
    setStoryCardOpen(true);
    if (event.yearStart !== null) setYear(event.yearStart);
  }, []);

  useEffect(() => {
    if (!timelineEvents.length) {
      setActiveEventId(null);
      setPlaying(false);
      return;
    }
    if (timelineEvents.some((event) => event.id === activeEventId)) return;
    activateTimelineEvent(timelineEvents[0]!);
  }, [activateTimelineEvent, activeEventId, timelineEvents]);

  useEffect(() => {
    if (!playing || !timelineEvents.length) return;
    const timer = window.setTimeout(() => {
      const nextIndex = nextTimelineEventIndex(timelineEvents, activeEventId);
      const nextEvent = timelineEvents[nextIndex];
      if (nextEvent) activateTimelineEvent(nextEvent);
    }, 3200);
    return () => window.clearTimeout(timer);
  }, [activateTimelineEvent, activeEventId, timelineEvents, playing]);

  useEffect(() => {
    if (!timelineExpanded || !activeEventId) return;
    timelineEventRefs.current.get(activeEventId)?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
      inline: "center",
    });
  }, [activeEventId, timelineExpanded]);
  const entityTypes = useMemo(
    () => [
      ...new Set((catalog?.points ?? []).map((point) => point.entityType)),
    ],
    [catalog],
  );
  const dynasties = useMemo(
    () => [
      ...new Set((catalog?.points ?? []).flatMap((point) => point.dynasties)),
    ],
    [catalog],
  );

  useEffect(() => {
    if (selectedId && !points.some((point) => point.id === selectedId)) {
      setSelectedId(null);
      setDetailSheetOpen(false);
    }
  }, [points, selectedId]);

  const selectRoute = useCallback(
    (routeId: string) => {
      setActiveRouteId(routeId || null);
      const route = catalog?.routes.find((item) => item.id === routeId);
      setRouteStopIds(route?.stopIds ?? []);
      setPlannedRoute(null);
    },
    [catalog],
  );

  const selectMapMode = (mode: MapMode) => {
    setMapMode(mode);
    setDetailSheetOpen(false);
    setToolPanel(mode === "route" ? "route" : null);
  };

  const openToolPanel = (panel: MapToolPanel) => {
    setDetailSheetOpen(false);
    setToolPanel(panel);
  };

  const clearFilters = () => {
    setQuery("");
    setDynasty("all");
    setEntityType("all");
    setMinConfidence("speculative");
    setIncludeUnknownTime(true);
    setRecordScope("all");
    setAppliedQuery("");
    setAppliedDynasty("all");
    setAppliedEntityType("all");
    setAppliedMinConfidence("speculative");
    setAppliedIncludeUnknownTime(true);
    setAppliedRecordScope("all");
  };

  const applyFilters = () => {
    if (!catalog) return;

    setAppliedQuery(query);
    setAppliedDynasty(dynasty);
    setAppliedEntityType(entityType);
    setAppliedMinConfidence(minConfidence);
    setAppliedIncludeUnknownTime(includeUnknownTime);
    setAppliedRecordScope(recordScope);

    const nextPoints = filterMapPoints(catalog.points, {
      query,
      dynasties: dynasty === "all" ? undefined : [dynasty],
      minConfidence,
      entityTypes: entityType === "all" ? undefined : [entityType],
      year,
      includeUnknownTime,
      recordScopes: recordScope === "all" ? undefined : [recordScope],
    });
    setSelectedId((current) =>
      nextPoints.some((point) => point.id === current) ? current : null,
    );
  };

  const stopLocationTracking = () => {
    if (locationWatchIdRef.current !== null && navigator.geolocation) {
      navigator.geolocation.clearWatch(locationWatchIdRef.current);
      locationWatchIdRef.current = null;
    }
    setLocationTracking(false);
    setLocating(false);
  };

  const locateUser = () => {
    if (locationTracking && userLocation) {
      setLocationFocusToken((value) => value + 1);
      return;
    }
    if (!navigator.geolocation) {
      setLocationError("当前浏览器不支持定位");
      return;
    }
    if (!window.isSecureContext) {
      setLocationError("实时定位需要通过 HTTPS 或 localhost 安全连接访问");
      return;
    }
    setLocating(true);
    setLocationError(null);
    locationWatchIdRef.current = navigator.geolocation.watchPosition(
      (position) => {
        setUserLocation({
          lon: position.coords.longitude,
          lat: position.coords.latitude,
          accuracyMeters: position.coords.accuracy,
        });
        setLocationTracking(true);
        setLocationFocusToken((value) => value + 1);
        setLocating(false);
      },
      (reason) => {
        setLocationError(
          reason.code === reason.PERMISSION_DENIED
            ? "定位权限被拒绝，请在浏览器地址栏中允许位置权限"
            : "暂时无法获取当前位置",
        );
        setLocating(false);
        if (reason.code === reason.PERMISSION_DENIED) {
          stopLocationTracking();
        }
      },
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 5_000 },
    );
  };

  const calculateRoadRoute = async () => {
    const coordinates = [
      ...(userLocation
        ? [{ lon: userLocation.lon, lat: userLocation.lat, name: "我的位置" }]
        : []),
      ...routeStops.map((point) => ({
        lon: point.lon,
        lat: point.lat,
        name: point.name,
      })),
    ];
    if (coordinates.length < 2) {
      setRouteError("至少保留两个站点，或先定位当前位置");
      return;
    }
    setRoutePlanning(true);
    setRouteError(null);
    try {
      const route = await planMapRoute(coordinates);
      setPlannedRoute(route);
      if (route.routingStatus === "unavailable") {
        setRouteError("道路服务暂不可用，当前红色虚线仅表示站点顺序");
      }
    } catch (reason) {
      setRouteError(reason instanceof Error ? reason.message : "无法规划路线");
    } finally {
      setRoutePlanning(false);
    }
  };

  if (!catalog && !error) {
    return <BusinessLoadingState label="正在读取古舆地图资料…" />;
  }
  if (!catalog && error) {
    return (
      <BusinessErrorState
        title="地图资料暂时无法加载"
        description={error}
        onRetry={() => setReloadKey((value) => value + 1)}
      />
    );
  }
  if (!catalog) return null;

  const filtersPanel = (
    <>
      <SheetHeader className="border-b px-5 py-4 pr-12">
        <SheetTitle>筛选点位</SheetTitle>
      </SheetHeader>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <form
          aria-label="地图筛选"
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault();
            applyFilters();
          }}
        >
          <div className="flex items-center justify-end">
            <button
              type="button"
              onClick={clearFilters}
              className="text-muted-foreground hover:text-foreground inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs"
            >
              <FilterX className="size-3.5" /> 清空
            </button>
          </div>
          <label className="block text-xs">
            关键词
            <input
              className="border-input mt-1 h-10 w-full rounded-md border px-3 text-sm"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="园林、寺庙、桥梁…"
            />
          </label>
          <fieldset>
            <legend className="mb-1 text-xs">资料层级</legend>
            <div className="grid grid-cols-3 gap-1 rounded-md bg-[#edf3f2] p-1">
              {(
                [
                  ["all", "全部"],
                  ["formal", "正式/参照"],
                  ["draft", "语料草稿"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={recordScope === value}
                  onClick={() => setRecordScope(value)}
                  className={cn(
                    "min-h-9 rounded px-2 text-xs",
                    recordScope === value
                      ? "bg-white font-medium text-[#174f53] shadow-sm"
                      : "text-[#52686c]",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </fieldset>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-xs">
              历史时期
              <select
                className="border-input mt-1 h-10 w-full rounded-md border px-2 text-sm"
                value={dynasty}
                onChange={(event) =>
                  setDynasty(event.target.value as DynastyLayer | "all")
                }
              >
                <option value="all">全部</option>
                {dynasties.map((item) => (
                  <option key={item} value={item}>
                    {dynastyLabels[item]}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-xs">
              实体类型
              <select
                className="border-input mt-1 h-10 w-full rounded-md border px-2 text-sm"
                value={entityType}
                onChange={(event) => setEntityType(event.target.value)}
              >
                <option value="all">全部</option>
                {entityTypes.map((item) => (
                  <option key={item} value={item}>
                    {entityTypeLabels[item] ?? item}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="block text-xs">
            最低定位可靠程度
            <select
              className="border-input mt-1 h-10 w-full rounded-md border px-2 text-sm"
              value={minConfidence}
              onChange={(event) =>
                setMinConfidence(event.target.value as SpatialConfidence)
              }
            >
              {(["speculative", "approximate", "exact"] as const).map(
                (item) => (
                  <option key={item} value={item}>
                    {confidenceLabels[item]}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="flex min-h-10 items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={includeUnknownTime}
              onChange={(event) => setIncludeUnknownTime(event.target.checked)}
            />
            保留年代尚待复核的现存点位
          </label>
          <button
            type="submit"
            className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-[#1d6267] px-3 text-sm font-medium text-white hover:bg-[#174f53]"
          >
            <Filter className="size-4" />
            应用筛选
          </button>
        </form>

        <section className="mt-6 border-t pt-4" aria-label="当前筛选结果">
          <h3 className="mb-2 text-sm font-medium">
            当前筛选结果（{points.length}）
          </h3>
          {points.length === 0 ? (
            <p className="text-muted-foreground text-sm leading-6">
              没有符合当前条件的点位，请放宽时期或定位可靠程度条件。
            </p>
          ) : (
            <ul className="space-y-1">
              {points.map((point) => (
                <li key={point.id}>
                  <button
                    type="button"
                    className={cn(
                      "flex min-h-10 w-full items-center justify-between gap-3 rounded-md px-2 text-left text-sm hover:bg-[#eef5f4]",
                      selectedId === point.id &&
                        "bg-[#e4f0ef] font-medium text-[#276b75]",
                    )}
                    onClick={() => selectPoint(point.id)}
                  >
                    <span className="truncate">{point.name}</span>
                    <span className="text-muted-foreground shrink-0 text-xs">
                      {entityTypeLabels[point.entityType] ?? point.entityType}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );

  const layersPanel = (
    <>
      <SheetHeader className="border-b px-5 py-4 pr-12">
        <SheetTitle>图层与人物轨迹</SheetTitle>
      </SheetHeader>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <section aria-label="地图图层">
          <p className="text-muted-foreground mb-4 text-xs leading-5">
            纸张底色与低对比度现代底图只承担定位；历史地图仅在完成校准后叠加。
            史料范围由资料本身提供，不等同于现代边界。
          </p>
          {catalog.layers.map((layer) => (
            <div
              key={layer.id}
              className="mb-5 border-b border-dashed pb-4 text-xs leading-5 last:border-b-0"
              data-map-layer-id={layer.id}
            >
              <div className="flex items-start justify-between gap-2">
                <label className="flex min-h-8 min-w-0 items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`显示${layer.name}`}
                    checked={enabledMapLayerIds.includes(layer.id)}
                    disabled={!layer.available || !layer.tileUrl}
                    onChange={(event) => {
                      setVisibleLayerIds((current) => {
                        const next = new Set(current ?? enabledMapLayerIds);
                        if (event.target.checked) next.add(layer.id);
                        else next.delete(layer.id);
                        return [...next];
                      });
                    }}
                  />
                  <span className="truncate font-medium">{layer.name}</span>
                </label>
                <span
                  className={cn(
                    "shrink-0 rounded px-1.5 py-0.5",
                    layer.available && layer.tileUrl
                      ? enabledMapLayerIds.includes(layer.id)
                        ? "bg-emerald-50 text-emerald-700"
                        : "bg-slate-100 text-slate-600"
                      : "bg-amber-50 text-amber-800",
                  )}
                >
                  {!layer.available || !layer.tileUrl
                    ? "待校准"
                    : enabledMapLayerIds.includes(layer.id)
                      ? "显示中"
                      : "已隐藏"}
                </span>
              </div>
              {layer.available && layer.tileUrl && (
                <label className="text-muted-foreground mt-2 flex items-center gap-2">
                  <span className="w-10 shrink-0">透明度</span>
                  <input
                    type="range"
                    min="0.1"
                    max="0.8"
                    step="0.02"
                    aria-label={`${layer.name}透明度`}
                    value={
                      layerOpacity[layer.id] ?? defaultMapLayerOpacity(layer)
                    }
                    onChange={(event) =>
                      setLayerOpacity((current) => ({
                        ...current,
                        [layer.id]: Number(event.target.value),
                      }))
                    }
                    className="min-w-0 flex-1 accent-[#2b6467]"
                  />
                  <output className="w-9 text-right tabular-nums">
                    {Math.round(
                      (layerOpacity[layer.id] ??
                        defaultMapLayerOpacity(layer)) * 100,
                    )}
                    %
                  </output>
                </label>
              )}
              <p className="text-muted-foreground mt-1">
                {layer.calibrationNote}
              </p>
              <a
                href={layer.sourceUrl}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-flex min-h-8 items-center gap-1 text-[#276b75] hover:underline"
              >
                查看来源 <ExternalLink className="size-3" />
              </a>
            </div>
          ))}
        </section>

        <section className="border-t pt-4" aria-label="人物活动节点">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-medium">人物活动节点</h3>
              {trajectory && (
                <p className="text-muted-foreground mt-1 text-xs">
                  {trajectory.personName}
                </p>
              )}
            </div>
            <label className="flex min-h-10 items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={showTrajectory}
                onChange={(event) => setShowTrajectory(event.target.checked)}
              />
              显示
            </label>
          </div>
          {catalog.trajectories.length > 1 && (
            <label className="mt-2 block text-xs">
              选择人物
              <select
                className="border-input mt-1 h-9 w-full rounded-md border px-2 text-xs"
                value={trajectory?.id ?? ""}
                onChange={(event) => {
                  setSelectedTrajectoryId(event.target.value);
                  setShowTrajectory(true);
                }}
              >
                {catalog.trajectories.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.personName} · {item.points.length} 个节点
                  </option>
                ))}
              </select>
            </label>
          )}
          {trajectory ? (
            <div className="mt-2 text-xs leading-5">
              <p className="text-muted-foreground">{trajectory.summary}</p>
              {trajectory.reviewStatus && (
                <p className="mt-1 font-medium text-amber-800">
                  {reviewLabels[trajectory.reviewStatus]}
                </p>
              )}
              <div className="mt-2 flex items-start gap-1.5 rounded bg-amber-50 px-2 py-1.5 text-amber-900">
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                <span>{trajectory.disclaimer}</span>
              </div>
            </div>
          ) : (
            <p className="text-muted-foreground mt-2 text-xs leading-5">
              暂无满足“时间 + 地点 + 资料出处”条件的人物活动节点。
            </p>
          )}
        </section>

        <p className="text-muted-foreground mt-5 border-t pt-4 text-xs leading-5">
          {catalog.dataNotice}
        </p>
      </div>
    </>
  );

  const routePanel = (
    <>
      <SheetHeader className="border-b px-5 py-4 pr-12">
        <SheetTitle>研学路线</SheetTitle>
      </SheetHeader>
      <section
        aria-label="研学路线"
        className="min-h-0 flex-1 overflow-y-auto px-5 py-4"
      >
        <select
          aria-label="选择研学路线"
          className="border-input h-10 w-full rounded-md border px-3 text-sm"
          value={activeRouteId ?? ""}
          onChange={(event) => selectRoute(event.target.value)}
        >
          {catalog.routes.map((route) => (
            <option key={route.id} value={route.id}>
              {route.name}
            </option>
          ))}
        </select>
        {activeRoute && (
          <>
            <div className="mt-4 flex items-start justify-between gap-3">
              <h3 className="text-sm font-semibold text-[#183f42]">
                {activeRoute.name}
              </h3>
              <span className="shrink-0 rounded bg-[#edf3f2] px-2 py-1 text-[11px] text-[#315f63]">
                {activeRoute.duration === "half_day" ? "半日" : "一日"}
              </span>
            </div>
            <p className="text-muted-foreground mt-3 text-xs leading-5">
              {activeRoute.summary}
            </p>
            <ol className="mt-3 space-y-1">
              {routeStops.map((stop, index) => (
                <li
                  key={stop.id}
                  className="flex min-w-0 items-center gap-1 text-xs"
                >
                  <span className="w-5 shrink-0 text-right text-[#718184]">
                    {index + 1}.
                  </span>
                  <button
                    type="button"
                    className="min-h-10 min-w-0 flex-1 truncate rounded-md px-2 text-left hover:bg-[#eef5f4] hover:text-[#276b75]"
                    onClick={() => selectPoint(stop.id)}
                  >
                    {stop.name}
                  </button>
                  <button
                    type="button"
                    aria-label={`上移${stop.name}`}
                    title="上移站点"
                    disabled={index === 0}
                    onClick={() =>
                      setRouteStopIds((items) => {
                        setPlannedRoute(null);
                        return moveItem(items, index, -1);
                      })
                    }
                    className="grid size-9 shrink-0 place-items-center rounded-md hover:bg-[#eef5f4] disabled:opacity-30"
                  >
                    <ArrowUp className="size-4" />
                  </button>
                  <button
                    type="button"
                    aria-label={`下移${stop.name}`}
                    title="下移站点"
                    disabled={index === routeStops.length - 1}
                    onClick={() =>
                      setRouteStopIds((items) => {
                        setPlannedRoute(null);
                        return moveItem(items, index, 1);
                      })
                    }
                    className="grid size-9 shrink-0 place-items-center rounded-md hover:bg-[#eef5f4] disabled:opacity-30"
                  >
                    <ArrowDown className="size-4" />
                  </button>
                  <button
                    type="button"
                    aria-label={`移除${stop.name}`}
                    title="移除站点"
                    onClick={() => {
                      setRouteStopIds((items) =>
                        items.filter((id) => id !== stop.id),
                      );
                      setPlannedRoute(null);
                    }}
                    className="grid size-9 shrink-0 place-items-center rounded-md hover:bg-[#eef5f4]"
                  >
                    <X className="size-4" />
                  </button>
                </li>
              ))}
            </ol>

            <div className="mt-4 grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={locateUser}
                disabled={locating}
                className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-md border px-2.5 text-xs hover:bg-[#eef5f4] disabled:opacity-40"
              >
                <LocateFixed className="size-4" />
                {locating ? "定位中…" : userLocation ? "更新位置" : "定位位置"}
              </button>
              <button
                type="button"
                onClick={() => void calculateRoadRoute()}
                disabled={routePlanning}
                className="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-md bg-[#245f64] px-2.5 text-xs text-white disabled:opacity-40"
              >
                <RouteIcon className="size-4" />
                {routePlanning ? "规划中…" : "道路规划（驾车）"}
              </button>
              <button
                type="button"
                onClick={() =>
                  downloadRoute(
                    activeRoute.name,
                    routeStops,
                    activeRoute.disclaimer,
                  )
                }
                className="col-span-2 inline-flex min-h-10 items-center justify-center gap-1.5 rounded-md border px-2.5 text-xs hover:bg-[#eef5f4]"
              >
                <Download className="size-4" /> 导出研学提纲
              </button>
            </div>
            {plannedRoute?.routingStatus === "routed" &&
              plannedRoute.distanceMeters !== null &&
              plannedRoute.durationSeconds !== null && (
                <p className="mt-3 text-xs text-[#315f68]">
                  道路路线约 {(plannedRoute.distanceMeters / 1000).toFixed(1)}{" "}
                  公里， 预计驾驶{" "}
                  {Math.max(1, Math.round(plannedRoute.durationSeconds / 60))}{" "}
                  分钟
                </p>
              )}
            {routeError && (
              <p className="mt-3 text-xs leading-5 text-amber-800">
                {routeError}
              </p>
            )}
            <p className="text-muted-foreground mt-5 border-t pt-3 text-xs leading-5">
              {activeRoute.disclaimer}
            </p>
          </>
        )}
      </section>
    </>
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#f7faf9]">
      <header className="flex min-h-16 items-center gap-3 border-b bg-white px-4 py-3">
        <SidebarTrigger />
        <MapIcon className="size-4 shrink-0 text-[#2b6467]" />
        <div className="min-w-0">
          <h1 className="text-base font-semibold">古舆地图</h1>
          <p className="text-muted-foreground truncate text-xs">
            木渎历史空间 · 现状定位 · 更新于 {catalog.updatedAt}
          </p>
        </div>
        <span className="ml-auto shrink-0 rounded border border-[#b9d9ca] bg-[#e7f3ec] px-2 py-1 text-xs whitespace-nowrap text-[#276947]">
          {catalog.points.length}
          <span className="hidden sm:inline"> 个可追溯</span>点位
        </span>
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <main className="flex min-w-0 flex-1 flex-col bg-[#edf2ef]">
          <section className="relative min-h-0 flex-1">
            <MapLibreCanvas
              points={points}
              layers={catalog.layers}
              visibleLayerIds={enabledMapLayerIds}
              layerOpacity={layerOpacity}
              routePoints={mapMode === "route" ? routeStops : []}
              trajectoryPoints={trajectoryPoints}
              plannedRoute={mapMode === "route" ? plannedRoute : null}
              userLocation={userLocation}
              locationFocusToken={locationFocusToken}
              events={catalog.events}
              historyYear={year}
              activeEventId={activeEventId}
              selectedId={selectedId}
              onSelect={(point) => selectPoint(point.id)}
              onSelectEvent={(event) => {
                setPlaying(false);
                activateTimelineEvent(event);
                selectPoint(event.pointId);
              }}
            />

            {activeEvent && storyCardOpen && (
              <article
                aria-label="历史故事镜头"
                data-map-story-card="true"
                className="absolute top-20 right-3 z-10 w-[min(21rem,calc(100%-1.5rem))] rounded-md border border-[#cba995] bg-[#fffdf8]/95 p-4 text-[#372b27] shadow-[0_12px_34px_rgba(48,37,31,0.2)] backdrop-blur"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[11px] font-medium tracking-[0.08em] text-[#8a5b45]">
                      历史镜头 · {activeEvent.timeLabel}
                    </p>
                    <h2 className="mt-1 text-base leading-6 font-semibold">
                      {activeEvent.title}
                    </h2>
                  </div>
                  <button
                    type="button"
                    aria-label="关闭历史故事镜头"
                    title="关闭历史故事镜头"
                    onClick={() => setStoryCardOpen(false)}
                    className="grid size-7 shrink-0 place-items-center rounded hover:bg-[#f4e8df]"
                  >
                    <X className="size-4" />
                  </button>
                </div>
                <p className="mt-2 text-xs leading-5 text-[#5e4b43]">
                  史料记载：{activeEvent.summary}
                </p>
                {(activeEvent.participants?.length ?? 0) > 0 && (
                  <p className="mt-2 text-xs leading-5 text-[#6f5143]">
                    相关人物：
                    {activeEvent.participants
                      ?.map((participant) => participant.name)
                      .join("、")}
                  </p>
                )}
                {activePointEvents.length > 1 && (
                  <section className="mt-3 border-t border-[#ead8cd] pt-2">
                    <p className="flex items-center gap-1 text-[11px] font-medium text-[#80533f]">
                      <CalendarRange className="size-3.5" /> 同地点沿革
                    </p>
                    <p className="mt-1 text-[10px] leading-4 text-[#9a7767]">
                      按资料时间排序；相邻不等同于因果关系。
                    </p>
                    <div className="mt-1.5 flex gap-1.5 overflow-x-auto pb-1">
                      {activePointEvents.map((event) => (
                        <button
                          key={event.id}
                          type="button"
                          onClick={() => activateTimelineEvent(event)}
                          className={cn(
                            "min-w-28 rounded border px-2 py-1.5 text-left text-[10px] leading-4",
                            event.id === activeEvent.id
                              ? "border-[#b67a5e] bg-[#f8eee8] text-[#5e3526]"
                              : "border-[#ead8cd] bg-white/70 text-[#765f54] hover:bg-[#f8eee8]",
                          )}
                        >
                          <span className="block font-medium">
                            {event.timeLabel}
                          </span>
                          <span className="mt-0.5 line-clamp-2 block">
                            {event.title}
                          </span>
                        </button>
                      ))}
                    </div>
                  </section>
                )}
                {activePointRelations.length > 0 && (
                  <section className="mt-3 border-t border-[#ead8cd] pt-2">
                    <p className="flex items-center gap-1 text-[11px] font-medium text-[#80533f]">
                      <Network className="size-3.5" /> 资料关联
                    </p>
                    <ul className="mt-1.5 space-y-1 text-[10px] leading-4 text-[#6f5143]">
                      {activePointRelations.slice(0, 6).map((relation) => (
                        <li key={relation.id}>{relationSentence(relation)}</li>
                      ))}
                    </ul>
                  </section>
                )}
                <div className="mt-3 border-t border-[#ead8cd] pt-2 text-[11px] leading-5 text-[#80533f]">
                  <span className="font-medium">依据：</span>
                  {activeEvent.evidence.length ? (
                    activeEvent.evidence.map((source) => (
                      <a
                        key={source.id}
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                        className="ml-1 inline underline decoration-[#cba995] underline-offset-2 hover:text-[#5e3526]"
                      >
                        {source.title}
                      </a>
                    ))
                  ) : (
                    <span className="ml-1">当前事件暂无来源链接</span>
                  )}
                  {activeEvent.evidence.some((source) => source.quote) && (
                    <div className="mt-2 space-y-1 border-t border-[#ead8cd] pt-2">
                      {activeEvent.evidence.map(
                        (source) =>
                          source.quote && (
                            <blockquote
                              key={`${source.id}-quote`}
                              className="border-l-2 border-[#cba995] pl-2 text-[#72564a]"
                            >
                              <Quote className="mr-1 inline size-3" />“
                              {source.quote}”
                            </blockquote>
                          ),
                      )}
                    </div>
                  )}
                  {!activeEvent.evidence.some(
                    (source) => (source.media?.length ?? 0) > 0,
                  ) && (
                    <p className="mt-2 flex items-center gap-1.5 border-t border-dashed border-[#ead8cd] pt-2 text-[10px] leading-4 text-[#8b7467]">
                      <ImageOff className="size-3 shrink-0" />
                      暂无授权影像、碑刻拓本或三维模型
                    </p>
                  )}
                </div>
                <p className="mt-2 text-[10px] leading-4 text-[#9a7767]">
                  镜头方向仅用于阅读聚焦，不表示史料中的真实行进路线。
                </p>
              </article>
            )}

            <div className="absolute top-3 left-3 z-10 flex max-w-[calc(100%-5rem)] items-center gap-1 rounded-md border border-[#cfdddc] bg-white/95 p-1 shadow-sm backdrop-blur">
              <div
                role="tablist"
                aria-label="地图模式"
                className="flex items-center rounded bg-[#edf3f2] p-0.5"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={mapMode === "explore"}
                  onClick={() => selectMapMode("explore")}
                  className={cn(
                    "inline-flex h-8 items-center gap-1.5 rounded px-2.5 text-xs font-medium",
                    mapMode === "explore"
                      ? "bg-white text-[#174f53] shadow-sm"
                      : "text-[#52686c] hover:text-[#174f53]",
                  )}
                >
                  <Compass className="size-3.5" /> 空间探索
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={mapMode === "route"}
                  onClick={() => selectMapMode("route")}
                  className={cn(
                    "inline-flex h-8 items-center gap-1.5 rounded px-2.5 text-xs font-medium",
                    mapMode === "route"
                      ? "bg-white text-[#174f53] shadow-sm"
                      : "text-[#52686c] hover:text-[#174f53]",
                  )}
                >
                  <RouteIcon className="size-3.5" /> 研学路线
                </button>
              </div>
              <span className="mx-0.5 h-5 w-px bg-[#d6e0df]" />
              <button
                type="button"
                aria-label="筛选点位"
                title="筛选点位"
                onClick={() => openToolPanel("filters")}
                className="inline-flex size-8 items-center justify-center rounded text-[#315f63] hover:bg-[#edf3f2]"
              >
                <Filter className="size-4" />
              </button>
              <button
                type="button"
                aria-label="地图图层"
                title="地图图层"
                onClick={() => openToolPanel("layers")}
                className="inline-flex size-8 items-center justify-center rounded text-[#315f63] hover:bg-[#edf3f2]"
              >
                <Layers3 className="size-4" />
              </button>
              <button
                type="button"
                aria-label={
                  locating
                    ? "正在获取位置"
                    : locationTracking
                      ? "居中我的位置"
                      : "开启实时定位"
                }
                title={locationTracking ? "居中我的位置" : "开启实时定位"}
                onClick={locateUser}
                disabled={locating}
                className={cn(
                  "inline-flex size-8 items-center justify-center rounded hover:bg-[#edf3f2] disabled:opacity-40",
                  locationTracking
                    ? "bg-blue-50 text-blue-700"
                    : "text-[#315f63]",
                )}
              >
                <LocateFixed
                  className={cn("size-4", locating && "animate-pulse")}
                />
              </button>
              {mapMode === "route" && (
                <button
                  type="button"
                  aria-label="编辑研学路线"
                  title="编辑研学路线"
                  onClick={() => openToolPanel("route")}
                  className="inline-flex size-8 items-center justify-center rounded text-[#315f63] hover:bg-[#edf3f2]"
                >
                  <RouteIcon className="size-4" />
                </button>
              )}
            </div>

            {(locationTracking || locationError) && (
              <div className="absolute right-3 bottom-12 z-10 flex max-w-[min(80vw,360px)] items-center gap-2 rounded-md border border-[#cfdddc] bg-white/95 px-2.5 py-2 text-xs shadow-sm backdrop-blur">
                {locationTracking ? (
                  <>
                    <span className="relative flex size-2.5 shrink-0">
                      <span className="absolute inline-flex size-full animate-ping rounded-full bg-blue-500 opacity-50 motion-reduce:animate-none" />
                      <span className="relative inline-flex size-2.5 rounded-full bg-blue-600" />
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        setLocationFocusToken((value) => value + 1)
                      }
                      className="truncate font-medium text-blue-800 hover:underline"
                    >
                      实时定位中
                      {userLocation
                        ? ` · 约 ${Math.round(userLocation.accuracyMeters)} 米`
                        : ""}
                    </button>
                    <button
                      type="button"
                      aria-label="停止实时定位"
                      title="停止实时定位"
                      onClick={stopLocationTracking}
                      className="grid size-7 shrink-0 place-items-center rounded hover:bg-[#edf3f2]"
                    >
                      <X className="size-3.5" />
                    </button>
                  </>
                ) : (
                  <span className="leading-5 text-amber-800">
                    {locationError}
                  </span>
                )}
              </div>
            )}

            <div
              data-map-legend="true"
              className="pointer-events-none absolute bottom-3 left-3 flex max-w-[calc(100%-5rem)] flex-wrap gap-x-2 gap-y-0.5 rounded bg-white/92 px-2 py-1 text-[11px] shadow-sm"
            >
              <span className="font-medium text-[#6f594c]">
                古今对照 · 现代底图已弱化
              </span>
              <span className="text-[#275e57]">▧ 史料范围</span>
              <span className="text-teal-800">● 精确点</span>
              <span className="text-amber-700">▧ 近似范围</span>
              <span className="text-rose-700">▧ 推测范围</span>
              <span className="text-[#52686c]">范围颜色不表示统计概率</span>
              <span className="text-amber-900">◈ 虚边为待复核语料草稿</span>
              {mapMode === "route" && (
                <span className="text-[#52686c]">实线为研学站点顺序</span>
              )}
              {userLocation && (
                <span className="text-blue-700">● 我的实时位置</span>
              )}
            </div>
          </section>

          <section
            className="shrink-0 border-t bg-white"
            aria-label="历史时间轴"
          >
            <div className="flex min-h-12 items-center gap-2 px-3 sm:px-4">
              <button
                type="button"
                title={playing ? "暂停时间播放" : "播放时间轴"}
                aria-label={playing ? "暂停时间播放" : "播放时间轴"}
                onClick={() => setPlaying((value) => !value)}
                className="grid size-9 shrink-0 place-items-center rounded-md border hover:bg-[#eef5f4]"
              >
                {playing ? (
                  <Pause className="size-4" />
                ) : (
                  <Play className="size-4" />
                )}
              </button>
              <CalendarRange className="size-4 shrink-0 text-[#315f63]" />
              <span className="min-w-0 flex-1 text-sm font-medium">
                历史时间轴
              </span>
              <strong className="max-w-[45vw] truncate text-sm sm:max-w-none">
                {activeEvent?.timeLabel ?? "暂无精选事件"}
              </strong>
              <button
                type="button"
                aria-label={
                  timelineExpanded ? "收起历史时间轴" : "展开历史时间轴"
                }
                aria-expanded={timelineExpanded}
                onClick={() => setTimelineExpanded((value) => !value)}
                className="grid size-9 shrink-0 place-items-center rounded-md hover:bg-[#eef5f4]"
              >
                {timelineExpanded ? (
                  <ChevronDown className="size-4" />
                ) : (
                  <ChevronUp className="size-4" />
                )}
              </button>
            </div>
            {timelineExpanded && (
              <div className="border-t px-3 py-2 sm:px-4">
                <div
                  ref={timelineScrollRef}
                  data-timeline-scale-start={timelineLayout.scale?.startYear}
                  data-timeline-scale-end={timelineLayout.scale?.endYear}
                  className="overflow-x-auto pb-1"
                >
                  {timelineEvents.length ? (
                    <div
                      className="relative"
                      style={{
                        width: timelineLayout.widthPx,
                        minHeight: timelineLayout.heightPx + 30,
                      }}
                    >
                      <div className="absolute top-6 right-0 left-0 h-px bg-[#c8d9d7]" />
                      {timelineLayout.ticks.map((tick) => (
                        <span
                          key={tick.year}
                          className="absolute top-0 -translate-x-1/2 text-[10px] text-[#718286]"
                          style={{ left: tick.leftPx }}
                        >
                          {tick.year}
                        </span>
                      ))}
                      {timelineLayout.items.map(
                        ({ event, leftPx, lane }, index) => (
                          <button
                            type="button"
                            key={event.id}
                            ref={(element) => {
                              if (element)
                                timelineEventRefs.current.set(
                                  event.id,
                                  element,
                                );
                              else timelineEventRefs.current.delete(event.id);
                            }}
                            onClick={() => {
                              setPlaying(false);
                              activateTimelineEvent(event);
                            }}
                            aria-current={
                              event.id === activeEventId ? "step" : undefined
                            }
                            aria-label={`查看历史事件：${event.title}`}
                            className={cn(
                              "absolute z-[1] flex w-[156px] -translate-x-1/2 flex-col items-center gap-1 bg-white px-1 text-center text-xs",
                              event.id === activeEventId
                                ? "font-medium text-[#174f53]"
                                : "text-[#5b6d70] hover:text-[#174f53]",
                            )}
                            style={{ top: 28 + lane * 68, left: leftPx }}
                          >
                            <span
                              className={cn(
                                "grid size-3.5 place-items-center rounded-full border-2 bg-white",
                                event.id === activeEventId
                                  ? "border-[#1d6267] ring-4 ring-[#d6e9e5]"
                                  : event.importance === "landmark"
                                    ? "border-[#4d8588]"
                                    : "border-[#9bb7b6]",
                              )}
                            />
                            <span className="block text-[10px] leading-4 text-[#8a6a5b]">
                              {event.timeLabel}
                            </span>
                            <span className="line-clamp-2 min-h-8 leading-4">
                              {event.title}
                            </span>
                            <span className="sr-only">
                              第 {index + 1} 个事件，{event.timeLabel}
                            </span>
                          </button>
                        ),
                      )}
                    </div>
                  ) : (
                    <span className="text-muted-foreground text-xs">
                      当前资料范围暂无历史事件
                    </span>
                  )}
                  {undatedTimelineEvents.length > 0 && (
                    <div className="mt-2 flex items-center gap-2 border-t border-dashed pt-2 text-xs">
                      <span className="shrink-0 text-[#8a6a5b]">年代待考</span>
                      <div className="flex gap-1.5 overflow-x-auto">
                        {undatedTimelineEvents.map((event) => (
                          <button
                            key={event.id}
                            type="button"
                            aria-label={`查看历史事件：${event.title}`}
                            onClick={() => {
                              setPlaying(false);
                              activateTimelineEvent(event);
                            }}
                            className={cn(
                              "max-w-48 rounded border px-2 py-1 text-left text-[11px] leading-4",
                              event.id === activeEventId
                                ? "border-[#b67a5e] bg-[#f8eee8] text-[#5e3526]"
                                : "border-[#d8e2e0] text-[#5b6d70] hover:bg-[#eef5f4]",
                            )}
                          >
                            {event.title}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        </main>

        {selected && (
          <aside className="hidden w-[390px] shrink-0 border-l bg-white xl:flex xl:min-h-0">
            <PointDetails
              point={selected}
              events={catalog.events}
              relations={catalog.relations}
              dataNotice={catalog.dataNotice}
              onClose={() => setSelectedId(null)}
            />
          </aside>
        )}
      </div>

      <Sheet
        open={toolPanel !== null}
        onOpenChange={(open) => {
          if (!open) setToolPanel(null);
        }}
      >
        <SheetContent
          side="left"
          className="w-[min(92vw,400px)] gap-0 p-0 sm:max-w-[400px]"
        >
          {toolPanel === "filters" && filtersPanel}
          {toolPanel === "layers" && layersPanel}
          {toolPanel === "route" && routePanel}
        </SheetContent>
      </Sheet>

      <Sheet
        open={compactLayout && detailSheetOpen && selected !== null}
        onOpenChange={setDetailSheetOpen}
      >
        {selected && (
          <SheetContent
            side="bottom"
            className="max-h-[84dvh] gap-0 rounded-t-md p-0 xl:hidden"
          >
            <SheetHeader className="sr-only">
              <SheetTitle>{selected.name}</SheetTitle>
            </SheetHeader>
            <PointDetails
              point={selected}
              events={catalog.events}
              relations={catalog.relations}
              dataNotice={catalog.dataNotice}
            />
          </SheetContent>
        )}
      </Sheet>
    </div>
  );
}
