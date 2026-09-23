"use client";

import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  type Edge,
  type Node,
  type NodeChange,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Database,
  FileSearch,
  MapPinned,
  Plus,
  Search,
  Share2,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
  BusinessEmptyState,
  BusinessErrorState,
  BusinessLoadingState,
  BusinessMobileHeader,
  BusinessPageHeader,
} from "@/components/workspace/business-page";
import { GraphReviewControls } from "@/components/workspace/graph-review-controls";
import { GraphOverview } from "@/components/workspace/graph-overview";
import { useAuth } from "@/core/auth/AuthProvider";
import {
  createEntity,
  createEvent,
  createRelation,
  extractTextKnowledge,
  fetchGraphCatalog,
  invalidateGraphCatalogCache,
  listAllEvents,
  listGeoFeatures,
  queryGraph,
  readCachedGraphCatalog,
  reviewEvent,
  reviewRelation,
  upsertGeoFeature,
} from "@/core/knowledge-graph/api";
import {
  filterRelationsForScope,
  type GraphScope,
} from "@/core/knowledge-graph/filters";
import {
  GRAPH_CENTER,
  connectedGraphComponents,
  layoutGraphEntities,
  layoutGraphOverview,
  type GraphPosition,
} from "@/core/knowledge-graph/layout";
import {
  matchesReviewFilter,
  reviewLabels,
  type ReviewFilterValue,
} from "@/core/knowledge-graph/review";
import { sortHistoricalEvents } from "@/core/knowledge-graph/types";
import type {
  EntityType,
  ExtractionResponse,
  GeoFeature,
  GraphEntity,
  GraphQueryResult,
  GraphRelation,
  HistoricalEvent,
  ReviewStatus,
} from "@/core/knowledge-graph/types";
import { createLatestRequestTracker } from "@/core/source-files/latest-request";

type View = "graph" | "events" | "geo";
type GraphMode = "explore" | "overview";
const entityTypes: Array<{ value: EntityType; label: string }> = [
  { value: "person", label: "人物" },
  { value: "family", label: "家族" },
  { value: "place", label: "地点" },
  { value: "waterway", label: "水系" },
  { value: "bridge", label: "桥梁" },
  { value: "building", label: "建筑" },
  { value: "garden", label: "园林" },
  { value: "relic", label: "文物" },
  { value: "organization", label: "机构" },
  { value: "work", label: "著作" },
  { value: "event", label: "事件" },
];
const relationLabels: Record<GraphRelation["relation_type"], string> = {
  located_in: "位于",
  built_by: "由其营建",
  repaired_in: "修缮于",
  crosses: "跨越",
  related_to: "相关",
  sibling_of: "兄弟姐妹",
  spouse_of: "配偶",
  parent_of: "父母",
  lived_in: "居住于",
  visited: "游览/到访",
  born_in: "出生于",
  worked_at: "任职于",
  studied_at: "求学于",
  died_at: "卒于/死于",
  composed_at: "在此赋诗",
  mentioned_in_poetry: "诗文提及",
  documented_in: "出自文献",
};
const reverseRelationLabels: Record<GraphRelation["relation_type"], string> = {
  located_in: "包含",
  built_by: "营建了",
  repaired_in: "修缮了",
  crosses: "被其跨越",
  related_to: "相关",
  sibling_of: "兄弟姐妹",
  spouse_of: "配偶",
  parent_of: "子女",
  lived_in: "居住者",
  visited: "到访者",
  born_in: "出生者",
  worked_at: "任职者",
  studied_at: "求学者",
  died_at: "卒者",
  composed_at: "在此赋诗者",
  mentioned_in_poetry: "诗文提及者",
  documented_in: "收录内容",
};
const LOCAL_GRAPH_MAX_NODES = 200;
const VISIBLE_GRAPH_RELATION_LIMIT = 18;
const VISIBLE_NETWORK_RELATION_LIMIT = 80;
type GraphDepth = 1 | 2 | 3;
const DEFAULT_GRAPH_DEPTH: GraphDepth = 2;
const entityNodeStyles: Record<
  EntityType,
  { border: string; background: string }
> = {
  person: { border: "#7b5e3b", background: "#fff8ed" },
  family: { border: "#806445", background: "#fbf2e8" },
  place: { border: "#477e78", background: "#edf7f4" },
  waterway: { border: "#3b7893", background: "#edf6fb" },
  bridge: { border: "#7b6b3f", background: "#faf7e9" },
  building: { border: "#8b5f55", background: "#fbf0ed" },
  garden: { border: "#4d8159", background: "#f0f8ec" },
  relic: { border: "#786b82", background: "#f5f0f8" },
  organization: { border: "#637487", background: "#f0f4f8" },
  work: { border: "#5b6972", background: "#f1f5f6" },
  event: { border: "#83664c", background: "#fbf4ec" },
};

function closePolygon(coordinates: Array<[number, number]>) {
  if (coordinates.length < 3) return coordinates;
  const first = coordinates[0]!;
  const last = coordinates.at(-1)!;
  return first[0] === last[0] && first[1] === last[1]
    ? coordinates
    : [...coordinates, first];
}

function relationLabelForCenter(relation: GraphRelation, centerId: string) {
  return relation.subject_id === centerId
    ? relationLabels[relation.relation_type]
    : reverseRelationLabels[relation.relation_type];
}

function orderVisibleGraphRelations(relations: GraphRelation[]) {
  // Keep the map readable while preserving relation diversity. Documentary
  // edges remain available in the side panel, but are the last candidates for
  // the visual neighborhood.
  const ordered = [...relations].sort(
    (left, right) =>
      Number(left.relation_type === "documented_in") -
        Number(right.relation_type === "documented_in") ||
      Number(left.is_inferred) - Number(right.is_inferred) ||
      right.evidence_ids.length - left.evidence_ids.length ||
      right.confidence - left.confidence ||
      left.id.localeCompare(right.id),
  );
  const selected: GraphRelation[] = [];
  const selectedTypes = new Set<GraphRelation["relation_type"]>();
  for (const relation of ordered) {
    if (selectedTypes.has(relation.relation_type)) continue;
    selected.push(relation);
    selectedTypes.add(relation.relation_type);
  }
  for (const relation of ordered) {
    if (selected.includes(relation)) continue;
    selected.push(relation);
  }
  return selected;
}

function selectVisibleGraphRelations(
  relations: GraphRelation[],
  limit: number,
  page: number,
): GraphRelation[] {
  const ordered = orderVisibleGraphRelations(relations);
  const start = page * limit;
  return ordered.slice(start, start + limit);
}

function buildLocalFocusedGraphResult(
  centerId: string,
  entities: GraphEntity[],
  relations: GraphRelation[],
): GraphQueryResult | null {
  const center = entities.find((entity) => entity.id === centerId);
  if (!center) return null;
  const groundedRelations = relations.filter(
    (relation) =>
      relation.review_status !== "rejected" &&
      (relation.evidence_ids.length > 0 || relation.is_inferred) &&
      (relation.subject_id === centerId || relation.object_id === centerId),
  );
  const entityById = new Map(entities.map((entity) => [entity.id, entity]));
  const nodeIds = new Set<string>([centerId]);
  for (const relation of groundedRelations) {
    nodeIds.add(relation.subject_id);
    nodeIds.add(relation.object_id);
  }
  return {
    query: center.canonical_name,
    status: "supported",
    message: "已预览载入的直接关系，正在查询所选范围的关系网。",
    candidates: [center],
    nodes: [...nodeIds]
      .map((entityId) => entityById.get(entityId))
      .filter((entity): entity is GraphEntity => Boolean(entity)),
    edges: groundedRelations,
    evidence: [],
    truncated: false,
    max_depth: 1,
  };
}

export default function KnowledgeGraphPage() {
  const { user } = useAuth();
  const isAdmin = user?.system_role === "admin";
  const [manageGraph, setManageGraph] = useState(false);
  const [initialGraphCatalog] = useState(readCachedGraphCatalog);
  const [view, setView] = useState<View>("graph");
  const discoveryView = view === "graph" && !(isAdmin && manageGraph);
  const [entities, setEntities] = useState<GraphEntity[]>(
    initialGraphCatalog?.entities ?? [],
  );
  const [relations, setRelations] = useState<GraphRelation[]>(
    initialGraphCatalog?.relations ?? [],
  );
  const [events, setEvents] = useState<HistoricalEvent[]>([]);
  const [geo, setGeo] = useState<GeoFeature[]>([]);
  const [result, setResult] = useState<GraphQueryResult | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(initialGraphCatalog === null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focusedEntityId, setFocusedEntityId] = useState<string | null>(null);
  const [focusLoading, setFocusLoading] = useState(false);
  const [focusHistory, setFocusHistory] = useState<string[]>([]);
  const [nodePositions, setNodePositions] = useState<
    Record<string, GraphPosition>
  >({});
  const previousFocusedEntityId = useRef<string | null>(null);
  const queryTracker = useRef(createLatestRequestTracker());
  const focusTracker = useRef(createLatestRequestTracker());
  const supportDataTracker = useRef(createLatestRequestTracker());
  const flowInstance = useRef<ReactFlowInstance | null>(null);
  const resultRequestSequence = useRef(0);
  const [selectedRelationId, setSelectedRelationId] = useState<string | null>(
    null,
  );
  const [graphMode, setGraphMode] = useState<GraphMode>("explore");
  const graphModeRef = useRef<GraphMode>("explore");
  const overviewReturnEntityId = useRef<string | null>(null);
  const overviewReturnReleaseId = useRef<string | null>(null);
  const [graphScope, setGraphScope] = useState<GraphScope>("all");
  const [graphDepth, setGraphDepth] = useState<GraphDepth>(DEFAULT_GRAPH_DEPTH);
  const graphDepthRef = useRef<GraphDepth>(DEFAULT_GRAPH_DEPTH);
  const [graphRelationPage, setGraphRelationPage] = useState(0);
  const [reviewFilter, setReviewFilter] = useState<ReviewFilterValue>("all");
  const rejectedView = isAdmin && reviewFilter === "rejected";

  useEffect(() => {
    const params = new URL(window.location.href).searchParams;
    const initialView = params.get("view");
    if (params.get("manage") === "1") setManageGraph(true);
    if (initialView === "events" || initialView === "geo") setView(initialView);
    const filter = params.get("review");
    if (filter === "reviewed" || filter === "draft" || filter === "rejected")
      setReviewFilter(filter);
  }, []);

  function changeReviewFilter(filter: ReviewFilterValue) {
    setReviewFilter(filter);
    const url = new URL(window.location.href);
    url.searchParams.set("review", filter);
    window.history.replaceState(null, "", url);
  }

  function changeView(next: View) {
    setView(next);
    const url = new URL(window.location.href);
    url.searchParams.set("view", next);
    window.history.replaceState(null, "", url);
  }
  const [entityForm, setEntityForm] = useState({
    canonical_name: "",
    entity_type: "place" as EntityType,
    summary: "",
  });
  const [relationForm, setRelationForm] = useState({
    subject_id: "",
    object_id: "",
    relation_type: "related_to" as GraphRelation["relation_type"],
  });
  const [eventForm, setEventForm] = useState({
    title: "",
    event_type: "historical_note",
    place_entity_id: "",
    summary: "",
  });
  const [geoForm, setGeoForm] = useState({
    entity_id: "",
    name: "",
    lon: "120.5067",
    lat: "31.2530",
    basis: "演示定位，待资料复核",
    geometry_type: "uncertainty_radius" as
      | "uncertainty_radius"
      | "historical_area",
    uncertainty_radius_m: "2500",
    area_coordinates: "",
    extent_source: "editorial_estimate" as
      | "evidence"
      | "historical_map"
      | "editorial_estimate",
    extent_basis: "研究人员估计范围，待史料地图或实地复核",
  });
  const [extractionText, setExtractionText] = useState("");
  const [extraction, setExtraction] = useState<ExtractionResponse | null>(null);

  const load = useCallback(
    async (force = false) => {
      const request = supportDataTracker.current.start();
      setLoading(true);
      setError(null);
      try {
        if (view === "graph") {
          if (discoveryView) return;
          const { entities: nextEntities, relations: nextRelations } =
            await fetchGraphCatalog({
              force,
              signal: request.signal,
              includeRejected: rejectedView,
            });
          if (!supportDataTracker.current.isCurrent(request.sequence)) return;
          setEntities(nextEntities);
          setRelations(nextRelations);
          if (rejectedView) return;
          if (graphModeRef.current === "overview") {
            setFocusedEntityId(null);
            setFocusHistory([]);
            setQuery("");
            setResult(null);
            return;
          }
          const degreeByEntity = new Map<string, number>();
          for (const relation of nextRelations) {
            if (relation.relation_type === "documented_in") continue;
            degreeByEntity.set(
              relation.subject_id,
              (degreeByEntity.get(relation.subject_id) ?? 0) + 1,
            );
            degreeByEntity.set(
              relation.object_id,
              (degreeByEntity.get(relation.object_id) ?? 0) + 1,
            );
          }
          const savedFocusId = new URL(window.location.href).searchParams.get(
            "entity",
          );
          const defaultFocus =
            nextEntities.find((entity) => entity.id === savedFocusId) ??
            [...nextEntities]
              .filter((entity) => (degreeByEntity.get(entity.id) ?? 0) > 0)
              .sort(
                (left, right) =>
                  (degreeByEntity.get(right.id) ?? 0) -
                    (degreeByEntity.get(left.id) ?? 0) ||
                  Number(right.entity_type === "person") -
                    Number(left.entity_type === "person") ||
                  left.canonical_name.localeCompare(right.canonical_name),
              )[0];
          setFocusedEntityId(defaultFocus?.id ?? null);
          setFocusHistory([]);
          setQuery((current) =>
            current.trim() ? current : (defaultFocus?.canonical_name ?? ""),
          );
          if (defaultFocus) {
            setResult(
              buildLocalFocusedGraphResult(
                defaultFocus.id,
                nextEntities,
                nextRelations,
              ),
            );
            const detailRequest = focusTracker.current.start();
            const resultSequence = ++resultRequestSequence.current;
            setFocusLoading(true);
            void (async () => {
              try {
                const initialResult = await queryGraph(
                  defaultFocus.id,
                  graphDepthRef.current,
                  {
                    maxNodes: LOCAL_GRAPH_MAX_NODES,
                    signal: detailRequest.signal,
                  },
                );
                if (
                  focusTracker.current.isCurrent(detailRequest.sequence) &&
                  resultRequestSequence.current === resultSequence
                ) {
                  setResult(initialResult);
                  if (initialResult.status !== "supported")
                    setFocusedEntityId(null);
                }
              } catch (reason) {
                if (
                  focusTracker.current.isCurrent(detailRequest.sequence) &&
                  resultRequestSequence.current === resultSequence
                ) {
                  setError(
                    reason instanceof Error
                      ? reason.message
                      : "关系网加载失败，当前保留已载入的直接关系",
                  );
                }
              } finally {
                if (
                  focusTracker.current.isCurrent(detailRequest.sequence) &&
                  resultRequestSequence.current === resultSequence
                )
                  setFocusLoading(false);
                focusTracker.current.finish(detailRequest.sequence);
              }
            })();
          }
        } else if (view === "events") {
          const nextEvents = await listAllEvents({
            includeRejected: rejectedView,
            signal: request.signal,
          });
          if (!supportDataTracker.current.isCurrent(request.sequence)) return;
          setEvents(nextEvents);
        } else if (view === "geo") {
          const nextGeo = await listGeoFeatures({
            limit: 200,
            signal: request.signal,
          });
          if (!supportDataTracker.current.isCurrent(request.sequence)) return;
          setGeo(nextGeo);
        }
      } catch (reason) {
        if (
          request.signal.aborted ||
          !supportDataTracker.current.isCurrent(request.sequence)
        ) {
          return;
        }
        setError(reason instanceof Error ? reason.message : "无法读取知识图谱");
      } finally {
        if (supportDataTracker.current.isCurrent(request.sequence)) {
          setLoading(false);
          supportDataTracker.current.finish(request.sequence);
        }
      }
    },
    [view, rejectedView, discoveryView],
  );
  useEffect(() => {
    const supportTracker = supportDataTracker.current;
    const queryRequestTracker = queryTracker.current;
    const focusRequestTracker = focusTracker.current;
    void load();
    return () => {
      supportTracker.cancel();
      queryRequestTracker.cancel();
      focusRequestTracker.cancel();
      resultRequestSequence.current += 1;
    };
  }, [load]);

  const graphEntities = useMemo(
    () => entities.filter((entity) => entity.evidence_ids.length > 0),
    [entities],
  );
  const graphRelations = useMemo(
    () =>
      relations.filter(
        (relation) =>
          relation.review_status !== "rejected" &&
          (relation.evidence_ids.length > 0 || relation.is_inferred),
      ),
    [relations],
  );
  const isGraphOverview = graphMode === "overview";
  const baseDisplayedRelations = useMemo(
    () =>
      isGraphOverview
        ? graphRelations
        : result
          ? result.status === "supported"
            ? result.edges
            : []
          : focusedEntityId
            ? graphRelations.filter(
                (relation) =>
                  relation.subject_id === focusedEntityId ||
                  relation.object_id === focusedEntityId,
              )
            : graphRelations,
    [focusedEntityId, graphRelations, isGraphOverview, result],
  );
  const baseDisplayedEntities = useMemo(
    () =>
      isGraphOverview
        ? graphEntities
        : result
          ? result.status === "supported"
            ? result.nodes
            : []
          : focusedEntityId
            ? graphEntities.filter(
                (entity) =>
                  entity.id === focusedEntityId ||
                  baseDisplayedRelations.some(
                    (relation) =>
                      relation.subject_id === entity.id ||
                      relation.object_id === entity.id,
                  ),
              )
            : graphEntities,
    [
      baseDisplayedRelations,
      focusedEntityId,
      graphEntities,
      isGraphOverview,
      result,
    ],
  );
  const relationPassesReview = useCallback(
    (relation: GraphRelation) =>
      matchesReviewFilter(relation.review_status, reviewFilter, isAdmin),
    [reviewFilter, isAdmin],
  );
  const graphEntitiesForScope = useMemo(() => {
    const entitiesById = new Map(
      [...entities, ...baseDisplayedEntities].map((entity) => [
        entity.id,
        entity,
      ]),
    );
    return [...entitiesById.values()];
  }, [baseDisplayedEntities, entities]);
  const displayedRelations = filterRelationsForScope(
    baseDisplayedRelations.filter(
      (relation) =>
        (isGraphOverview ||
          graphDepth > 1 ||
          !focusedEntityId ||
          relation.subject_id === focusedEntityId ||
          relation.object_id === focusedEntityId) &&
        relationPassesReview(relation),
    ),
    graphScope,
    graphEntitiesForScope,
  );
  const visibleRelationLimit =
    graphDepth === 1
      ? VISIBLE_GRAPH_RELATION_LIMIT
      : VISIBLE_NETWORK_RELATION_LIMIT;
  const graphRelationPageCount = Math.max(
    1,
    Math.ceil(displayedRelations.length / visibleRelationLimit),
  );
  const safeGraphRelationPage = Math.min(
    graphRelationPage,
    graphRelationPageCount - 1,
  );
  useEffect(() => {
    setGraphRelationPage(0);
  }, [focusedEntityId, graphScope, graphDepth, reviewFilter, result?.query]);
  useEffect(() => {
    if (graphRelationPage !== safeGraphRelationPage) {
      setGraphRelationPage(safeGraphRelationPage);
    }
  }, [graphRelationPage, safeGraphRelationPage]);
  const visibleGraphRelations = useMemo(
    () =>
      isGraphOverview
        ? displayedRelations
        : selectVisibleGraphRelations(
            displayedRelations,
            visibleRelationLimit,
            safeGraphRelationPage,
          ),
    [
      displayedRelations,
      isGraphOverview,
      safeGraphRelationPage,
      visibleRelationLimit,
    ],
  );
  const visibleGraphEntityIds = new Set(
    visibleGraphRelations.flatMap((relation) => [
      relation.subject_id,
      relation.object_id,
    ]),
  );
  const displayedEntities = baseDisplayedEntities.filter((entity) =>
    isGraphOverview
      ? graphScope === "all" ||
        entity.entity_type === "person" ||
        visibleGraphEntityIds.has(entity.id)
      : entity.id === focusedEntityId ||
        graphScope === "all" ||
        entity.entity_type === "person" ||
        visibleGraphEntityIds.has(entity.id),
  );
  const visibleGraphEntities = displayedEntities.filter(
    (entity) =>
      isGraphOverview ||
      entity.id === focusedEntityId ||
      visibleGraphEntityIds.has(entity.id),
  );
  const focusedEntity =
    (focusedEntityId &&
      displayedEntities.find((entity) => entity.id === focusedEntityId)) ??
    null;
  const entityById = useMemo(() => {
    const map = new Map<string, GraphEntity>();
    for (const entity of [...entities, ...displayedEntities]) {
      map.set(entity.id, entity);
    }
    return map;
  }, [displayedEntities, entities]);
  const focusedRelations = useMemo(
    () =>
      focusedEntityId
        ? displayedRelations.filter(
            (relation) =>
              relation.subject_id === focusedEntityId ||
              relation.object_id === focusedEntityId,
          )
        : [],
    [displayedRelations, focusedEntityId],
  );
  const panelRelations = isGraphOverview
    ? focusedRelations
    : graphDepth === 1
      ? focusedRelations
      : displayedRelations;
  const graphComponents = useMemo(
    () => connectedGraphComponents(displayedEntities, displayedRelations),
    [displayedEntities, displayedRelations],
  );
  const connectedComponentCount = graphComponents.filter(
    (component) => component.relationIds.length > 0,
  ).length;
  const isolatedEntityCount = graphComponents.filter(
    (component) => component.relationIds.length === 0,
  ).length;
  const evidenceById = useMemo(
    () =>
      new Map(
        (result?.evidence ?? []).map((item) => [
          String(item.evidence_id),
          item,
        ]),
      ),
    [result?.evidence],
  );
  const graphShapeKey = `${graphMode}|${visibleGraphEntities.map((entity) => entity.id).join(",")}|${visibleGraphRelations.map((relation) => relation.id).join(",")}|${focusedEntityId ?? ""}`;
  useEffect(() => {
    const recenter = previousFocusedEntityId.current !== focusedEntityId;
    previousFocusedEntityId.current = focusedEntityId;
    const defaults = isGraphOverview
      ? layoutGraphOverview(visibleGraphEntities, visibleGraphRelations)
      : layoutGraphEntities(
          visibleGraphEntities,
          visibleGraphRelations,
          focusedEntityId,
        );
    setNodePositions((current) => {
      let changed = false;
      const next: Record<string, GraphPosition> = {};
      for (const entity of visibleGraphEntities) {
        const existing = recenter ? undefined : current[entity.id];
        const fallback = defaults.get(entity.id) ?? { x: 520, y: 260 };
        next[entity.id] = existing ?? fallback;
        changed ||= existing === undefined;
      }
      if (Object.keys(current).some((id) => !next[id])) changed = true;
      return changed ? next : current;
    });
    // Only add positions for new nodes. A drag must survive subsequent renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphShapeKey]);
  const flow = useMemo(() => {
    const positions = isGraphOverview
      ? layoutGraphOverview(visibleGraphEntities, visibleGraphRelations)
      : layoutGraphEntities(
          visibleGraphEntities,
          visibleGraphRelations,
          focusedEntityId,
        );
    const nodes: Node[] = visibleGraphEntities.map((entity, index) => {
      const nodeStyle = entityNodeStyles[entity.entity_type];
      return {
        id: entity.id,
        position: nodePositions[entity.id] ??
          positions.get(entity.id) ?? {
            x: (index % 4) * 220,
            y: Math.floor(index / 4) * 130,
          },
        data: {
          label: `${entity.canonical_name}\n${entityTypes.find((item) => item.value === entity.entity_type)?.label ?? entity.entity_type}`,
        },
        style: {
          width: 170,
          whiteSpace: "pre-line",
          borderRadius: 6,
          border:
            entity.id === focusedEntityId
              ? "2px solid #174f53"
              : `1px solid ${entity.review_status === "reviewed" ? nodeStyle.border : "#c39a47"}`,
          background:
            entity.id === focusedEntityId ? "#dff2ef" : nodeStyle.background,
          color: "#203334",
          fontSize: 13,
          padding: 12,
          boxShadow:
            entity.id === focusedEntityId
              ? "0 0 0 3px rgba(41, 110, 114, 0.14)"
              : undefined,
        },
      };
    });
    const nodeIds = new Set(nodes.map((node) => node.id));
    const edges: Edge[] = visibleGraphRelations
      .filter(
        (relation) =>
          nodeIds.has(relation.subject_id) && nodeIds.has(relation.object_id),
      )
      .map((relation) => ({
        id: relation.id,
        source: relation.subject_id,
        target: relation.object_id,
        label: relationLabels[relation.relation_type],
        markerEnd: { type: MarkerType.ArrowClosed },
        animated: relation.is_inferred,
        style: { stroke: relation.is_inferred ? "#b7791f" : "#39737a" },
        labelStyle: { fontSize: 11, fill: "#4c5f62" },
      }));
    return { nodes, edges };
  }, [
    focusedEntityId,
    isGraphOverview,
    nodePositions,
    visibleGraphEntities,
    visibleGraphRelations,
  ]);

  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    const positionChanges = changes.filter(
      (
        change,
      ): change is NodeChange & {
        type: "position";
        position: { x: number; y: number };
      } => change.type === "position" && Boolean(change.position),
    );
    if (!positionChanges.length) return;
    setNodePositions((current) => {
      const next = { ...current };
      for (const change of positionChanges) next[change.id] = change.position;
      return next;
    });
  }, []);

  const centerGraphOn = useCallback((entityId: string) => {
    const instance = flowInstance.current;
    const node = instance?.getNode(entityId);
    if (!instance || !node) return;
    void instance.setCenter(node.position.x + 85, node.position.y + 32, {
      duration: 250,
      zoom: 0.82,
    });
  }, []);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      if (isGraphOverview) {
        void flowInstance.current?.fitView({
          padding: 0.12,
          minZoom: 0.08,
          maxZoom: 0.82,
          duration: 250,
        });
      } else if (!focusedEntityId) {
        return;
      } else if (graphDepth > 1) {
        void flowInstance.current?.fitView({
          padding: 0.18,
          minZoom: 0.12,
          maxZoom: 0.82,
          duration: 250,
        });
      } else {
        centerGraphOn(focusedEntityId);
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [
    centerGraphOn,
    focusedEntityId,
    graphDepth,
    graphShapeKey,
    isGraphOverview,
  ]);

  function showGraphOverview() {
    queryTracker.current.cancel();
    focusTracker.current.cancel();
    resultRequestSequence.current += 1;
    overviewReturnEntityId.current = focusedEntityId;
    overviewReturnReleaseId.current = result?.release_id ?? null;
    graphModeRef.current = "overview";
    setGraphMode("overview");
    setResult(null);
    setFocusedEntityId(null);
    setFocusHistory([]);
    setQuery("");
    setSelectedRelationId(null);
    setQueryLoading(false);
    setFocusLoading(false);
    setError(null);
  }

  function enterFocusedGraph(options: { restore?: boolean } = {}) {
    graphModeRef.current = "explore";
    setGraphMode("explore");
    if (options.restore && overviewReturnEntityId.current) {
      const entityId = overviewReturnEntityId.current;
      const releaseId = overviewReturnReleaseId.current;
      overviewReturnEntityId.current = null;
      overviewReturnReleaseId.current = null;
      void focusEntity(entityId, {
        addToHistory: false,
        releaseId: releaseId ?? undefined,
      });
    }
  }

  async function runQuery() {
    const normalizedQuery = query.trim();
    if (!normalizedQuery || queryLoading) return;
    enterFocusedGraph();
    focusTracker.current.cancel();
    setFocusLoading(false);
    const request = queryTracker.current.start();
    const resultSequence = ++resultRequestSequence.current;
    setQueryLoading(true);
    setError(null);
    const localEntity = entities.find(
      (entity) =>
        entity.id === normalizedQuery ||
        entity.canonical_name.localeCompare(normalizedQuery, "zh-CN", {
          sensitivity: "base",
        }) === 0,
    );
    if (localEntity) {
      setFocusedEntityId(localEntity.id);
      setResult(
        buildLocalFocusedGraphResult(localEntity.id, entities, relations),
      );
      centerGraphOn(localEntity.id);
    }
    try {
      const nextResult = await queryGraph(
        normalizedQuery,
        graphDepthRef.current,
        {
          maxNodes: LOCAL_GRAPH_MAX_NODES,
          signal: request.signal,
        },
      );
      if (
        !queryTracker.current.isCurrent(request.sequence) ||
        resultRequestSequence.current !== resultSequence
      ) {
        return;
      }
      setResult(nextResult);
      setFocusHistory([]);
      setFocusedEntityId(
        nextResult.status === "supported"
          ? (nextResult.candidates[0]?.id ?? null)
          : null,
      );
      if (nextResult.status === "supported" && nextResult.candidates[0]) {
        centerGraphOn(nextResult.candidates[0].id);
      }
      setSelectedRelationId(null);
    } catch (reason) {
      if (
        request.signal.aborted ||
        !queryTracker.current.isCurrent(request.sequence) ||
        resultRequestSequence.current !== resultSequence
      ) {
        return;
      }
      setError(reason instanceof Error ? reason.message : "图谱查询失败");
    } finally {
      if (
        queryTracker.current.isCurrent(request.sequence) &&
        resultRequestSequence.current === resultSequence
      ) {
        setQueryLoading(false);
        queryTracker.current.finish(request.sequence);
      }
    }
  }

  async function focusEntity(
    entityId: string,
    options: {
      addToHistory?: boolean;
      depth?: GraphDepth;
      releaseId?: string;
    } = {},
  ) {
    if (focusLoading || queryLoading) return;
    const entity = entityById.get(entityId);
    if (!entity) return;
    if (entityId === focusedEntityId && options.depth === undefined) return;
    const releaseId =
      options.releaseId ??
      result?.release_id ??
      (isGraphOverview ? overviewReturnReleaseId.current : null);
    if (isGraphOverview) overviewReturnReleaseId.current = null;
    enterFocusedGraph();
    if (
      options.addToHistory !== false &&
      focusedEntityId &&
      entityId !== focusedEntityId
    ) {
      setFocusHistory((current) => [...current, focusedEntityId].slice(-40));
    }
    queryTracker.current.cancel();
    setQueryLoading(false);
    const request = focusTracker.current.start();
    const resultSequence = ++resultRequestSequence.current;
    setFocusedEntityId(entityId);
    setQuery(entity.canonical_name);
    if (entityId !== focusedEntityId) {
      const preview = buildLocalFocusedGraphResult(
        entityId,
        result?.status === "supported" ? result.nodes : entities,
        result?.status === "supported" ? result.edges : relations,
      );
      setResult(
        preview
          ? {
              ...preview,
              release_id: result?.release_id,
              evidence: result?.evidence ?? [],
            }
          : null,
      );
    }
    setSelectedRelationId(null);
    centerGraphOn(entityId);
    setFocusLoading(true);
    setError(null);
    try {
      const nextResult = await queryGraph(
        entityId,
        options.depth ?? graphDepthRef.current,
        {
          maxNodes: LOCAL_GRAPH_MAX_NODES,
          releaseId: releaseId ?? undefined,
          signal: request.signal,
        },
      );
      if (
        !focusTracker.current.isCurrent(request.sequence) ||
        resultRequestSequence.current !== resultSequence
      ) {
        return;
      }
      setResult(nextResult);
    } catch (reason) {
      if (
        request.signal.aborted ||
        !focusTracker.current.isCurrent(request.sequence) ||
        resultRequestSequence.current !== resultSequence
      ) {
        return;
      }
      if (options.depth !== undefined) {
        graphDepthRef.current = graphDepth;
        setGraphDepth(graphDepth);
      }
      setError(reason instanceof Error ? reason.message : "关系加载失败");
    } finally {
      if (
        focusTracker.current.isCurrent(request.sequence) &&
        resultRequestSequence.current === resultSequence
      ) {
        setFocusLoading(false);
        focusTracker.current.finish(request.sequence);
      }
    }
  }

  function changeGraphDepth(depth: GraphDepth) {
    if (depth === graphDepth || focusLoading || queryLoading) return;
    graphDepthRef.current = depth;
    setGraphDepth(depth);
    if (focusedEntityId)
      void focusEntity(focusedEntityId, { addToHistory: false, depth });
  }

  function goBackToPreviousEntity() {
    const previousEntityId = focusHistory.at(-1);
    if (!previousEntityId || focusLoading) return;
    setFocusHistory((current) => current.slice(0, -1));
    void focusEntity(previousEntityId, { addToHistory: false });
  }

  async function save(action: () => Promise<unknown>, message: string) {
    setSaving(true);
    setError(null);
    try {
      await action();
      invalidateGraphCatalogCache();
      toast.success(message);
      await load(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function changeRelationReview(
    item: GraphRelation,
    status: ReviewStatus,
    note: string,
  ) {
    setSaving(true);
    setError(null);
    try {
      const updated = await reviewRelation(
        item.id,
        status,
        note,
        item.review_status,
      );
      const url = new URL(window.location.href);
      url.searchParams.set("entity", updated.subject_id);
      window.history.replaceState(null, "", url);
      invalidateGraphCatalogCache();
      setRelations((current) =>
        current.map((row) => (row.id === updated.id ? updated : row)),
      );
      // Cancel older traversals before applying the authoritative PATCH result.
      focusTracker.current.cancel();
      queryTracker.current.cancel();
      resultRequestSequence.current += 1;
      setFocusLoading(false);
      setQueryLoading(false);
      setResult((current) =>
        current
          ? {
              ...current,
              edges: current.edges.map((row) =>
                row.id === updated.id ? updated : row,
              ),
            }
          : current,
      );
      revealReviewResult(updated.review_status);
      toast.success(`关系审核结果：${reviewLabels[updated.review_status]}`);
    } finally {
      setSaving(false);
    }
  }

  async function changeEventReview(
    item: HistoricalEvent,
    status: ReviewStatus,
    note: string,
  ) {
    setSaving(true);
    setError(null);
    try {
      const updated = await reviewEvent(
        item.id,
        status,
        note,
        item.review_status,
      );
      invalidateGraphCatalogCache();
      setEvents((current) =>
        current.map((row) => (row.id === updated.id ? updated : row)),
      );
      revealReviewResult(updated.review_status);
      toast.success(`事件审核结果：${reviewLabels[updated.review_status]}`);
    } finally {
      setSaving(false);
    }
  }

  function revealReviewResult(status: ReviewStatus) {
    if (status === "rejected") changeReviewFilter("rejected");
    else if (!matchesReviewFilter(status, reviewFilter, isAdmin))
      changeReviewFilter("all");
  }

  async function runExtraction() {
    if (!extractionText.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const response = await extractTextKnowledge(extractionText.trim(), false);
      setExtraction(response);
      toast.success("抽取结果仅供预览，正式图谱只接收文献 Evidence");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "文本抽取失败");
    } finally {
      setSaving(false);
    }
  }

  if (!discoveryView && loading && !entities.length)
    return <BusinessLoadingState label="正在读取知识图谱…" />;
  if (!discoveryView && error && !entities.length)
    return (
      <BusinessErrorState description={error} onRetry={() => void load(true)} />
    );

  return (
    <main className="size-full overflow-y-auto bg-[#f7faf9] text-[#202d2e]">
      <BusinessMobileHeader title="知识图谱" />
      <div className="mx-auto max-w-7xl px-4 py-7 sm:px-8 lg:px-10 lg:py-9">
        <BusinessPageHeader
          title="知识图谱"
          description="从全局总览发现不同关系群组，选择主体探索，并回查文献出处"
          icon={Share2}
        />

        {!discoveryView && (
          <div className="mt-5 flex flex-col gap-3 border-b border-[#d7e1df] pb-4 md:flex-row">
            <label className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-md border bg-white px-3">
              <Search className="size-4 text-[#66797a]" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && void runQuery()}
                placeholder="输入实体名称或编号"
                className="min-w-0 flex-1 bg-transparent text-sm outline-none"
              />
            </label>
            <button
              type="button"
              disabled={queryLoading || !query.trim()}
              onClick={() => void runQuery()}
              className="h-10 rounded-md bg-[#245f64] px-4 text-sm text-white hover:bg-[#194d51] disabled:cursor-not-allowed disabled:opacity-45"
            >
              {queryLoading ? "查询中…" : "查询关系"}
            </button>
          </div>
        )}
        {!discoveryView && error && (
          <p className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}
        {!discoveryView && result && result.status !== "supported" && (
          <p className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {result.status === "ambiguous"
              ? "名称存在多个候选，请输入更具体的名称。"
              : "当前图谱没有匹配实体；管理员可在下方先建立待审核实体。"}
          </p>
        )}
        {!discoveryView &&
          result?.status === "supported" &&
          (result.truncated ||
            displayedRelations.length > visibleGraphRelations.length) && (
            <p className="mt-3 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              已载入 {displayedRelations.length} 条关系，当前图中显示{" "}
              {visibleGraphRelations.length} 条。右侧保留已载入的关系列表。
              {displayedRelations.length > visibleGraphRelations.length &&
                "可使用下方分页查看其他关系。"}
              {result.truncated &&
                "本次查询已达到范围上限，结果并非完整关系网；可点击其他主体继续探索。"}
            </p>
          )}

        <div className="mt-5 flex gap-1 border-b" role="tablist">
          {(
            [
              ["graph", "实体与关系", Database],
              ["events", "时间事件", CalendarDays],
              ["geo", "地图定位", MapPinned],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              onClick={() => changeView(id)}
              className={`inline-flex h-10 items-center gap-2 border-b-2 px-3 text-sm ${view === id ? "border-[#296e72] text-[#225b5f]" : "border-transparent text-[#697b7c]"}`}
            >
              <Icon className="size-4" />
              {label}
            </button>
          ))}
        </div>

        {view === "graph" && isAdmin && (
          <button
            type="button"
            className="mt-3 rounded border px-3 py-2 text-sm"
            onClick={() => setManageGraph((value) => !value)}
          >
            {manageGraph ? "返回全局浏览" : "打开审核与录入工作台"}
          </button>
        )}
        {discoveryView && (
          <GraphOverview key={user?.id ?? "anonymous"} isAdmin={isAdmin} />
        )}
        {view === "graph" && !discoveryView && (
          <section className="mt-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b pb-3">
              <div className="flex flex-wrap items-center gap-2">
                <div
                  className="flex rounded-md bg-[#eaf1ef] p-1"
                  role="group"
                  aria-label="图谱视图"
                >
                  <button
                    type="button"
                    aria-pressed={isGraphOverview}
                    disabled={loading || focusLoading || queryLoading}
                    onClick={showGraphOverview}
                    title="查看当前知识版本中的所有独立关系网"
                    className={`h-8 rounded px-3 text-xs disabled:cursor-wait disabled:opacity-60 ${isGraphOverview ? "bg-white font-medium text-[#225b5f] shadow-sm" : "text-[#68797a]"}`}
                  >
                    全图总览
                  </button>
                  <button
                    type="button"
                    aria-pressed={!isGraphOverview}
                    disabled={loading || focusLoading || queryLoading}
                    onClick={() => enterFocusedGraph({ restore: true })}
                    title="返回当前主体的多跳关系探索"
                    className={`h-8 rounded px-3 text-xs disabled:cursor-wait disabled:opacity-60 ${!isGraphOverview ? "bg-white font-medium text-[#225b5f] shadow-sm" : "text-[#68797a]"}`}
                  >
                    主体探索
                  </button>
                </div>
                {focusHistory.length > 0 && (
                  <button
                    type="button"
                    disabled={focusLoading}
                    onClick={goBackToPreviousEntity}
                    title="返回上一个探索主体"
                    className="inline-flex h-8 items-center gap-1.5 rounded border border-[#cbdad7] bg-white px-2.5 text-xs text-[#225f64] hover:bg-[#eef5f4] disabled:cursor-not-allowed disabled:opacity-45"
                  >
                    <ArrowLeft className="size-3.5" />
                    返回上一个主体
                  </button>
                )}
                <div
                  className="flex rounded-md bg-[#eaf1ef] p-1"
                  role="group"
                  aria-label="关系层数"
                >
                  {(
                    [
                      [1, "直接关系"],
                      [2, "两层关系网"],
                      [3, "三层关系网"],
                    ] as const
                  ).map(([depth, label]) => (
                    <button
                      key={depth}
                      type="button"
                      aria-pressed={graphDepth === depth}
                      disabled={
                        isGraphOverview ||
                        loading ||
                        focusLoading ||
                        queryLoading
                      }
                      onClick={() => changeGraphDepth(depth)}
                      className={`h-8 rounded px-3 text-xs disabled:cursor-wait disabled:opacity-60 ${graphDepth === depth ? "bg-white font-medium text-[#225b5f] shadow-sm" : "text-[#68797a]"}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div
                  className="flex rounded-md bg-[#eaf1ef] p-1"
                  aria-label="关系范围"
                >
                  {(
                    [
                      ["all", "全部关系类型"],
                      ["people", "人物关系"],
                    ] as const
                  ).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      aria-pressed={graphScope === value}
                      onClick={() => setGraphScope(value)}
                      title={
                        value === "all"
                          ? "查看人物、地点、建筑、事件等全部关系"
                          : "仅查看人物与人物之间的亲属和社会关系"
                      }
                      className={`h-8 rounded px-3 text-xs ${graphScope === value ? "bg-white font-medium text-[#225b5f] shadow-sm" : "text-[#68797a]"}`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <ReviewFilter
                value={reviewFilter}
                onChange={changeReviewFilter}
                isAdmin={isAdmin}
              />
            </div>
            {rejectedView ? (
              <section aria-label="已驳回关系审核">
                <p className="mb-3 text-sm text-[#68797a]">
                  已驳回关系仅在管理员审核列表中显示。改判后仍需通过后续发布流程对外生效。
                </p>
                <ul className="space-y-3">
                  {relations
                    .filter((item) => item.review_status === "rejected")
                    .map((item) => (
                      <li
                        key={item.id}
                        id={`graph-relation-${item.id}`}
                        className="rounded border bg-white p-4 text-sm"
                      >
                        <p>
                          {entityById.get(item.subject_id)?.canonical_name ??
                            item.subject_id}{" "}
                          · {relationLabels[item.relation_type]} ·{" "}
                          {entityById.get(item.object_id)?.canonical_name ??
                            item.object_id}
                        </p>
                        <p className="mt-1 text-amber-800">
                          审核状态：{reviewLabels[item.review_status]}
                        </p>
                        <div className="mt-2 text-xs">
                          {item.evidence_ids.map((evidenceId, index) => (
                            <a
                              key={evidenceId}
                              href={`/api/knowledge-search/evidence/${encodeURIComponent(evidenceId)}`}
                              target="_blank"
                              rel="noreferrer"
                              className="mr-3 text-[#24676c] hover:underline"
                            >
                              查看资料出处 {index + 1}
                            </a>
                          ))}
                        </div>
                        <GraphReviewControls
                          status={item.review_status}
                          hasEvidence={item.evidence_ids.length > 0}
                          disabled={saving}
                          onReview={(status, note) =>
                            changeRelationReview(item, status, note)
                          }
                        />
                      </li>
                    ))}
                </ul>
                {!loading &&
                  !relations.some(
                    (item) => item.review_status === "rejected",
                  ) && <p>暂无已驳回关系。</p>}
              </section>
            ) : (
              <>
                <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-[#dbe5e2] pb-3 text-xs text-[#68797a]">
                  <span>
                    {isGraphOverview
                      ? `全图总览 · ${connectedComponentCount} 个独立关系网${isolatedEntityCount ? ` · ${isolatedEntityCount} 个孤立主体` : ""}`
                      : focusedEntity
                        ? `以“${focusedEntity.canonical_name}”为中心 · 已载入 ${result?.max_depth ?? 1} 层关系`
                        : "从搜索或图中节点开始探索"}
                    {(focusLoading || queryLoading) && " · 正在加载关系网…"}
                  </span>
                  <span>
                    图中显示 {visibleGraphEntities.length} 个主体 · 已载入{" "}
                    {displayedRelations.length} 条关系
                  </span>
                </div>
                {!isGraphOverview && graphRelationPageCount > 1 && (
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded border border-[#dbe5e2] bg-white px-3 py-2 text-xs text-[#68797a]">
                    <span>
                      地图关系第 {safeGraphRelationPage + 1} /{" "}
                      {graphRelationPageCount} 组 · 本组{" "}
                      {visibleGraphRelations.length} 条
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        disabled={safeGraphRelationPage === 0}
                        onClick={() =>
                          setGraphRelationPage((current) =>
                            Math.max(0, current - 1),
                          )
                        }
                        title="查看上一组关系"
                        className="inline-flex h-7 items-center gap-1 rounded border border-[#cbdad7] bg-white px-2 text-xs text-[#225f64] hover:bg-[#eef5f4] disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <ChevronLeft className="size-3.5" />
                        上一组
                      </button>
                      <button
                        type="button"
                        disabled={
                          safeGraphRelationPage >= graphRelationPageCount - 1
                        }
                        onClick={() =>
                          setGraphRelationPage((current) =>
                            Math.min(graphRelationPageCount - 1, current + 1),
                          )
                        }
                        title="查看下一组关系"
                        className="inline-flex h-7 items-center gap-1 rounded border border-[#cbdad7] bg-white px-2 text-xs text-[#225f64] hover:bg-[#eef5f4] disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        下一组
                        <ChevronRight className="size-3.5" />
                      </button>
                    </div>
                  </div>
                )}
                <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
                  <div className="h-[680px] overflow-hidden rounded-md border bg-white lg:h-[760px]">
                    {flow.nodes.length ? (
                      <ReactFlow
                        nodes={flow.nodes}
                        edges={flow.edges}
                        minZoom={0.12}
                        maxZoom={1.6}
                        onInit={(instance) => {
                          flowInstance.current = instance;
                          if (isGraphOverview) {
                            void instance.fitView({
                              padding: 0.12,
                              minZoom: 0.08,
                              maxZoom: 0.82,
                            });
                          } else {
                            void instance.setCenter(
                              GRAPH_CENTER.x,
                              GRAPH_CENTER.y,
                              {
                                zoom: 0.82,
                              },
                            );
                          }
                        }}
                        onNodesChange={handleNodesChange}
                        nodesDraggable
                        nodesConnectable={false}
                        panOnDrag
                        zoomOnScroll
                        onNodeClick={(_, node) => {
                          if (
                            !focusLoading &&
                            !queryLoading &&
                            node.id !== focusedEntityId
                          ) {
                            void focusEntity(node.id);
                          }
                        }}
                        onEdgeClick={(_, edge) => {
                          setSelectedRelationId(edge.id);
                          document
                            .getElementById(`graph-relation-${edge.id}`)
                            ?.scrollIntoView({ block: "nearest" });
                        }}
                      >
                        <Background color="#dbe5e2" gap={32} />
                        <Controls showInteractive={false} />
                      </ReactFlow>
                    ) : (
                      <BusinessEmptyState
                        icon={Share2}
                        title="图谱尚无实体"
                        description="当前还没有绑定文献 Evidence 的实体。"
                        className="h-full"
                      />
                    )}
                  </div>
                  <aside className="max-h-[680px] overflow-y-auto border-l bg-white p-4 lg:max-h-[760px]">
                    {focusedEntity ? (
                      <>
                        <div className="border-b border-[#dbe5e2] pb-3">
                          <p className="text-xs text-[#718082]">当前探索中心</p>
                          <h2 className="mt-1 text-base font-semibold">
                            {focusedEntity.canonical_name}
                          </h2>
                          <p className="mt-1 text-xs text-[#718082]">
                            {entityTypes.find(
                              (item) =>
                                item.value === focusedEntity.entity_type,
                            )?.label ?? focusedEntity.entity_type}
                            {focusedEntity.summary
                              ? ` · ${focusedEntity.summary}`
                              : ""}
                          </p>
                        </div>
                        <div className="mt-3 flex items-center justify-between gap-2">
                          <h3 className="text-sm font-semibold">
                            {graphDepth === 1 ? "关联主体" : "关系记录"}（
                            {panelRelations.length}）
                          </h3>
                          {focusLoading && (
                            <span className="text-xs text-[#718082]">
                              加载中…
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-xs leading-5 text-[#718082]">
                          {graphDepth === 1
                            ? "当前显示主体的直接关系；切换到两层或三层关系网，可查看关联主体之间及更外围的联系。"
                            : "关系网包含当前主体及外围主体的联系。点击连线查看出处，点击主体可继续以它为中心探索。"}
                        </p>
                        <ul className="mt-3 space-y-3">
                          {panelRelations.map((relation) => {
                            const relationCenterId =
                              relation.subject_id === focusedEntity.id ||
                              relation.object_id === focusedEntity.id
                                ? focusedEntity.id
                                : relation.subject_id;
                            const otherId =
                              relation.subject_id === relationCenterId
                                ? relation.object_id
                                : relation.subject_id;
                            const other = entityById.get(otherId);
                            const evidence = relation.evidence_ids
                              .map((evidenceId) => evidenceById.get(evidenceId))
                              .filter((item): item is Record<string, unknown> =>
                                Boolean(item),
                              );
                            const isEvidenceOpen =
                              selectedRelationId === relation.id;
                            return (
                              <li
                                key={relation.id}
                                id={`graph-relation-${relation.id}`}
                                className="border-b border-[#e4ebea] pb-3 text-xs leading-5"
                              >
                                <div className="flex items-center gap-2">
                                  <span className="min-w-0 flex-1 truncate font-medium">
                                    {entityById.get(relationCenterId)
                                      ?.canonical_name ?? relationCenterId}
                                  </span>
                                  <ArrowRight className="size-3.5 shrink-0 text-[#7b9293]" />
                                  <button
                                    type="button"
                                    disabled={focusLoading || queryLoading}
                                    onClick={() => void focusEntity(otherId)}
                                    className="inline-flex min-w-0 items-center gap-1 truncate font-semibold text-[#24676c] hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    <span className="truncate">
                                      {other?.canonical_name ?? otherId}
                                    </span>
                                  </button>
                                </div>
                                <p className="mt-1 text-[#315f64]">
                                  {relationLabelForCenter(
                                    relation,
                                    relationCenterId,
                                  )}
                                  {relation.start_time || relation.end_time
                                    ? ` · ${relation.start_time ?? ""}${relation.end_time ? `—${relation.end_time}` : ""}`
                                    : ""}
                                </p>
                                <div className="mt-1 text-[#748385]">
                                  关系可靠程度{" "}
                                  {Math.round(relation.confidence * 100)}% ·{" "}
                                  {relation.is_inferred
                                    ? "推断关系"
                                    : `${relation.evidence_ids.length} 条资料出处`}
                                </div>
                                <p className="mt-1 text-amber-800">
                                  审核状态：
                                  {reviewLabels[relation.review_status]}
                                </p>
                                <button
                                  type="button"
                                  onClick={() =>
                                    setSelectedRelationId(
                                      isEvidenceOpen ? null : relation.id,
                                    )
                                  }
                                  className="mt-1 inline-flex items-center gap-1 text-[#24676c] hover:underline"
                                >
                                  <FileSearch className="size-3.5" />
                                  {isEvidenceOpen ? "收起出处" : "查看资料出处"}
                                </button>
                                {isEvidenceOpen && (
                                  <div className="mt-2 rounded border border-[#d9e4e2] bg-[#f6faf9] p-2 text-[#627477]">
                                    {evidence.length ? (
                                      evidence.map((item) => {
                                        const documentTitle =
                                          typeof item.document_title ===
                                          "string"
                                            ? item.document_title
                                            : "未命名资料";
                                        const volume =
                                          typeof item.volume === "string" ||
                                          typeof item.volume === "number"
                                            ? String(item.volume)
                                            : "";
                                        const pageStart =
                                          typeof item.page_start === "string" ||
                                          typeof item.page_start === "number"
                                            ? String(item.page_start)
                                            : "";
                                        return (
                                          <p key={String(item.evidence_id)}>
                                            {documentTitle}
                                            {volume || pageStart
                                              ? ` · ${volume}${pageStart ? ` 第${pageStart}页` : ""}`
                                              : ""}
                                          </p>
                                        );
                                      })
                                    ) : relation.evidence_ids.length ? (
                                      <div className="space-y-1">
                                        {relation.evidence_ids.map(
                                          (evidenceId, index) => (
                                            <a
                                              key={evidenceId}
                                              href={`/api/knowledge-search/evidence/${encodeURIComponent(evidenceId)}`}
                                              target="_blank"
                                              rel="noreferrer"
                                              className="block text-[#24676c] hover:underline"
                                            >
                                              查看资料出处 {index + 1}
                                            </a>
                                          ),
                                        )}
                                      </div>
                                    ) : (
                                      <p>当前关系尚未绑定资料出处。</p>
                                    )}
                                  </div>
                                )}
                                {isAdmin && (
                                  <GraphReviewControls
                                    status={relation.review_status}
                                    hasEvidence={
                                      relation.evidence_ids.length > 0
                                    }
                                    disabled={saving}
                                    onReview={(status, note) =>
                                      changeRelationReview(
                                        relation,
                                        status,
                                        note,
                                      )
                                    }
                                  />
                                )}
                              </li>
                            );
                          })}
                          {!panelRelations.length && (
                            <li className="text-sm text-[#718082]">
                              当前范围还没有可展示的关系。
                            </li>
                          )}
                        </ul>
                      </>
                    ) : isGraphOverview ? (
                      <>
                        <h2 className="text-sm font-semibold">
                          关系网总览（{connectedComponentCount}）
                        </h2>
                        <p className="mt-1 text-xs leading-5 text-[#718082]">
                          当前知识版本中有 {connectedComponentCount}{" "}
                          个互不相连的关系网。点击任意关系网的主体，即可进入对应的多跳探索。
                          {isolatedEntityCount
                            ? `另有 ${isolatedEntityCount} 个暂未形成关系的孤立主体。`
                            : ""}
                        </p>
                        <ul className="mt-3 space-y-3">
                          {graphComponents.map((component, index) => {
                            const firstEntityId = component.entityIds[0];
                            if (!firstEntityId) return null;
                            const names = component.entityIds
                              .map(
                                (entityId) =>
                                  entityById.get(entityId)?.canonical_name,
                              )
                              .filter((name): name is string => Boolean(name));
                            const isIsolated =
                              component.relationIds.length === 0;
                            return (
                              <li
                                key={component.id}
                                className="border-b border-[#e4ebea] pb-3 text-xs leading-5"
                              >
                                <div className="font-medium">
                                  {isIsolated
                                    ? "孤立主体"
                                    : `关系网 ${index + 1}`}
                                </div>
                                <div className="mt-1 text-[#748385]">
                                  {component.entityIds.length} 个主体 ·{" "}
                                  {component.relationIds.length} 条关系
                                </div>
                                <p className="mt-1 text-[#315f64]">
                                  {names.slice(0, 5).join("、")}
                                  {names.length > 5
                                    ? ` 等 ${names.length} 个主体`
                                    : ""}
                                </p>
                                <button
                                  type="button"
                                  disabled={focusLoading || queryLoading}
                                  onClick={() =>
                                    void focusEntity(firstEntityId, {
                                      addToHistory: false,
                                    })
                                  }
                                  className="mt-1 font-semibold text-[#24676c] hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  从此关系网开始探索
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      </>
                    ) : (
                      <>
                        <h2 className="text-sm font-semibold">
                          关系记录（{displayedRelations.length}）
                        </h2>
                        <p className="mt-1 text-xs leading-5 text-[#718082]">
                          点击图中的任意节点，开始以它为中心探索关系。
                        </p>
                        <ul className="mt-3 space-y-3">
                          {displayedRelations.map((relation) => (
                            <li
                              key={relation.id}
                              id={`graph-relation-${relation.id}`}
                              className="border-b pb-3 text-xs leading-5"
                            >
                              <div className="font-medium">
                                {entityById.get(relation.subject_id)
                                  ?.canonical_name ?? relation.subject_id}{" "}
                                · {relationLabels[relation.relation_type]} ·{" "}
                                {entityById.get(relation.object_id)
                                  ?.canonical_name ?? relation.object_id}
                              </div>
                              <div className="text-[#748385]">
                                关系可靠程度{" "}
                                {Math.round(relation.confidence * 100)}% ·{" "}
                                {relation.is_inferred
                                  ? "推断关系"
                                  : `${relation.evidence_ids.length} 条资料出处`}
                              </div>
                              <p className="mt-1 text-amber-800">
                                审核状态：{reviewLabels[relation.review_status]}
                              </p>
                              {isAdmin && (
                                <GraphReviewControls
                                  status={relation.review_status}
                                  hasEvidence={relation.evidence_ids.length > 0}
                                  disabled={saving}
                                  onReview={(status, note) =>
                                    changeRelationReview(relation, status, note)
                                  }
                                />
                              )}
                            </li>
                          ))}
                          {!displayedRelations.length && (
                            <li className="text-sm text-[#718082]">
                              当前没有关系记录。
                            </li>
                          )}
                        </ul>
                      </>
                    )}
                  </aside>
                </div>
              </>
            )}
          </section>
        )}
        {view === "events" && (
          <section className="mt-4">
            <div className="mb-3 flex justify-end border-b pb-3">
              <ReviewFilter
                value={reviewFilter}
                onChange={changeReviewFilter}
                isAdmin={isAdmin}
              />
            </div>
            <EventTimeline
              events={sortHistoricalEvents(events).filter((item) =>
                matchesReviewFilter(item.review_status, reviewFilter, isAdmin),
              )}
              entityById={entityById}
              isAdmin={isAdmin}
              saving={saving}
              onReview={changeEventReview}
            />
          </section>
        )}
        {view === "geo" && (
          <section className="mt-4">
            <div className="mb-3 flex items-center justify-between gap-3 border-b pb-3">
              <p className="text-xs text-[#68797a]">
                坐标为历史地点的现状参照，定位可靠程度与审核状态分别展示。
              </p>
              <Link
                href="/workspace/map"
                className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md border bg-white px-3 text-xs text-[#225f64] hover:bg-[#eef5f4]"
              >
                <MapPinned className="size-3.5" /> 在古舆地图查看
              </Link>
            </div>
            {geo.length ? (
              <ul className="divide-y border-y bg-white">
                {geo.map((item) => (
                  <li
                    key={item.entity_id}
                    className="grid gap-2 px-4 py-4 md:grid-cols-[220px_1fr_auto]"
                  >
                    <div>
                      <h2 className="text-sm font-semibold">{item.name}</h2>
                      <p className="mt-1 font-mono text-xs text-[#647779]">
                        {item.lon.toFixed(6)}, {item.lat.toFixed(6)}
                      </p>
                    </div>
                    <p className="text-xs leading-5 text-[#647779]">
                      {item.basis}
                    </p>
                    <div className="text-right text-xs">
                      <div>{item.confidence}</div>
                      <div className="mt-1 text-amber-800">
                        {reviewLabels[item.review_status]}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <BusinessEmptyState
                icon={MapPinned}
                title="当前没有数据库定位记录"
                description="古舆地图的公开资料目录仍可正常使用。"
              />
            )}
          </section>
        )}

        {isAdmin ? (
          <section className="mt-8 border-t pt-6">
            <div className="mb-4">
              <h2 className="text-base font-semibold">图谱数据维护</h2>
              <p className="mt-1 text-xs text-[#68797a]">
                文献导入会自动绑定
                Evidence。手工文本只允许预览，不能绕过文献证据写入正式图谱。
              </p>
            </div>
            <div className="mb-6 grid gap-4 border-b border-[#d8e2df] pb-6 lg:grid-cols-[minmax(0,1fr)_340px]">
              <div>
                <label
                  className="text-sm font-medium"
                  htmlFor="knowledge-extraction-text"
                >
                  文本知识抽取
                </label>
                <textarea
                  id="knowledge-extraction-text"
                  value={extractionText}
                  onChange={(event) => setExtractionText(event.target.value)}
                  rows={4}
                  placeholder="粘贴文献片段，仅预览可抽取的实体、关系和事件"
                  className="mt-2 w-full resize-y rounded-md border border-[#cedbd8] bg-white px-3 py-2 text-sm leading-6 outline-none"
                />
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void runExtraction()}
                    className="h-9 rounded-md border bg-white px-3 text-sm disabled:opacity-40"
                  >
                    预览抽取
                  </button>
                </div>
              </div>
              <div className="border-l border-[#d8e2df] pl-4 text-sm">
                <h3 className="font-medium">抽取结果</h3>
                {extraction ? (
                  <dl className="mt-2 grid grid-cols-[100px_1fr] gap-y-2 text-xs">
                    <dt className="text-[#718082]">实体</dt>
                    <dd>
                      {extraction.extraction.entities
                        .map((item) => item.name)
                        .join("、") || "无"}
                    </dd>
                    <dt className="text-[#718082]">关系</dt>
                    <dd>{extraction.extraction.relations.length} 条</dd>
                    <dt className="text-[#718082]">事件</dt>
                    <dd>{extraction.extraction.events.length} 条</dd>
                    <dt className="text-[#718082]">别名候选</dt>
                    <dd>
                      {extraction.extraction.aliases
                        .map((item) => `${item.alias} → ${item.canonical_name}`)
                        .join("、") || "无"}
                    </dd>
                    <dt className="text-[#718082]">写入状态</dt>
                    <dd>仅预览，未写入</dd>
                  </dl>
                ) : (
                  <p className="mt-2 text-xs leading-5 text-[#718082]">
                    先预览可检查规则结果；确认写入后，记录保持待审核状态，不直接发布。
                  </p>
                )}
              </div>
            </div>
            <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
              <AdminForm
                title="新建实体"
                onSubmit={() =>
                  save(() => createEntity(entityForm), "实体已建立")
                }
                saving={saving}
              >
                <input
                  required
                  value={entityForm.canonical_name}
                  onChange={(e) =>
                    setEntityForm({
                      ...entityForm,
                      canonical_name: e.target.value,
                    })
                  }
                  placeholder="名称，例如：演示桥"
                  className="field"
                />
                <select
                  value={entityForm.entity_type}
                  onChange={(e) =>
                    setEntityForm({
                      ...entityForm,
                      entity_type: e.target.value as EntityType,
                    })
                  }
                  className="field"
                >
                  {entityTypes.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
                <textarea
                  value={entityForm.summary}
                  onChange={(e) =>
                    setEntityForm({ ...entityForm, summary: e.target.value })
                  }
                  placeholder="简要说明"
                  className="field min-h-20 py-2"
                />
              </AdminForm>
              <AdminForm
                title="建立推断关系"
                onSubmit={() =>
                  save(
                    () =>
                      createRelation({
                        ...relationForm,
                        confidence: 0.5,
                        is_inferred: true,
                        review_status: "pending",
                      }),
                    "推断关系已建立",
                  )
                }
                saving={saving}
              >
                <EntitySelect
                  value={relationForm.subject_id}
                  entities={entities}
                  onChange={(value) =>
                    setRelationForm({ ...relationForm, subject_id: value })
                  }
                />
                <select
                  value={relationForm.relation_type}
                  onChange={(e) =>
                    setRelationForm({
                      ...relationForm,
                      relation_type: e.target
                        .value as GraphRelation["relation_type"],
                    })
                  }
                  className="field"
                >
                  {Object.entries(relationLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
                <EntitySelect
                  value={relationForm.object_id}
                  entities={entities}
                  onChange={(value) =>
                    setRelationForm({ ...relationForm, object_id: value })
                  }
                />
              </AdminForm>
              <AdminForm
                title="登记演示事件"
                onSubmit={() =>
                  save(() => createEvent(eventForm), "事件已登记")
                }
                saving={saving}
              >
                <input
                  required
                  value={eventForm.title}
                  onChange={(e) =>
                    setEventForm({ ...eventForm, title: e.target.value })
                  }
                  placeholder="事件标题"
                  className="field"
                />
                <EntitySelect
                  value={eventForm.place_entity_id}
                  entities={entities}
                  onChange={(value) =>
                    setEventForm({ ...eventForm, place_entity_id: value })
                  }
                />
                <textarea
                  value={eventForm.summary}
                  onChange={(e) =>
                    setEventForm({ ...eventForm, summary: e.target.value })
                  }
                  placeholder="内容，可只写一句话"
                  className="field min-h-20 py-2"
                />
              </AdminForm>
              <AdminForm
                title="登记推测点位"
                onSubmit={() =>
                  save(
                    () =>
                      upsertGeoFeature({
                        entity_id: geoForm.entity_id,
                        name: geoForm.name,
                        lon: Number(geoForm.lon),
                        lat: Number(geoForm.lat),
                        confidence: "speculative",
                        basis: geoForm.basis,
                        geometry_type: geoForm.geometry_type,
                        uncertainty_radius_m:
                          geoForm.geometry_type === "uncertainty_radius"
                            ? Number(geoForm.uncertainty_radius_m)
                            : null,
                        area_coordinates:
                          geoForm.geometry_type === "historical_area"
                            ? closePolygon(
                                geoForm.area_coordinates
                                  .split(/\r?\n/)
                                  .map(
                                    (line) =>
                                      line.split(",").map(Number) as [
                                        number,
                                        number,
                                      ],
                                  )
                                  .filter(([lon, lat]) =>
                                    Number.isFinite(lon + lat),
                                  ),
                              )
                            : [],
                        extent_source: geoForm.extent_source,
                        extent_basis: geoForm.extent_basis,
                        review_status: "pending",
                      }),
                    "点位已登记",
                  )
                }
                saving={saving}
              >
                <EntitySelect
                  value={geoForm.entity_id}
                  entities={entities}
                  onChange={(value) => {
                    const entity = entities.find((item) => item.id === value);
                    setGeoForm({
                      ...geoForm,
                      entity_id: value,
                      name: entity?.canonical_name ?? geoForm.name,
                    });
                  }}
                />
                <div className="grid grid-cols-2 gap-2">
                  <input
                    required
                    type="number"
                    step="any"
                    value={geoForm.lon}
                    onChange={(e) =>
                      setGeoForm({ ...geoForm, lon: e.target.value })
                    }
                    className="field"
                    aria-label="经度"
                  />
                  <input
                    required
                    type="number"
                    step="any"
                    value={geoForm.lat}
                    onChange={(e) =>
                      setGeoForm({ ...geoForm, lat: e.target.value })
                    }
                    className="field"
                    aria-label="纬度"
                  />
                </div>
                <select
                  value={geoForm.geometry_type}
                  onChange={(e) =>
                    setGeoForm({
                      ...geoForm,
                      geometry_type: e.target.value as
                        | "uncertainty_radius"
                        | "historical_area",
                    })
                  }
                  className="field"
                  aria-label="空间表达"
                >
                  <option value="uncertainty_radius">不确定半径</option>
                  <option value="historical_area">史料范围</option>
                </select>
                {geoForm.geometry_type === "uncertainty_radius" ? (
                  <input
                    required
                    type="number"
                    min="10"
                    max="100000"
                    value={geoForm.uncertainty_radius_m}
                    onChange={(e) =>
                      setGeoForm({
                        ...geoForm,
                        uncertainty_radius_m: e.target.value,
                      })
                    }
                    placeholder="范围半径（米）"
                    aria-label="范围半径（米）"
                    className="field"
                  />
                ) : (
                  <textarea
                    required
                    value={geoForm.area_coordinates}
                    onChange={(e) =>
                      setGeoForm({
                        ...geoForm,
                        area_coordinates: e.target.value,
                      })
                    }
                    placeholder={"120.49,31.24\n120.51,31.24\n120.51,31.26"}
                    aria-label="范围边界坐标"
                    className="field min-h-24 py-2 font-mono text-xs"
                  />
                )}
                <select
                  value={geoForm.extent_source}
                  onChange={(e) =>
                    setGeoForm({
                      ...geoForm,
                      extent_source: e.target.value as
                        | "evidence"
                        | "historical_map"
                        | "editorial_estimate",
                    })
                  }
                  className="field"
                  aria-label="范围来源"
                >
                  <option value="evidence">资料出处</option>
                  <option value="historical_map">历史舆图</option>
                  <option value="editorial_estimate">研究估计</option>
                </select>
                <input
                  required
                  value={geoForm.extent_basis}
                  onChange={(e) =>
                    setGeoForm({ ...geoForm, extent_basis: e.target.value })
                  }
                  placeholder="范围依据"
                  className="field"
                />
                <input
                  required
                  value={geoForm.basis}
                  onChange={(e) =>
                    setGeoForm({ ...geoForm, basis: e.target.value })
                  }
                  placeholder="定位依据"
                  className="field"
                />
              </AdminForm>
            </div>
          </section>
        ) : (
          <p className="mt-7 border-t pt-4 text-xs text-[#748385]">
            当前账号可查询图谱、事件与定位；数据维护仅向管理员开放。
          </p>
        )}
      </div>
    </main>
  );
}

function ReviewFilter({
  value,
  onChange,
  isAdmin,
}: {
  value: ReviewFilterValue;
  onChange: (value: ReviewFilterValue) => void;
  isAdmin: boolean;
}) {
  return (
    <div className="flex rounded-md bg-[#eaf1ef] p-1" aria-label="审核状态">
      {(
        [
          ["all", "全部状态"],
          ["reviewed", "已通过"],
          ["draft", "待复核/争议"],
          ...(isAdmin ? [["rejected", "已驳回"] as const] : []),
        ] as const
      ).map(([item, label]) => (
        <button
          key={item}
          type="button"
          aria-pressed={value === item}
          onClick={() => onChange(item)}
          className={`h-8 rounded px-3 text-xs ${value === item ? "bg-white font-medium text-[#225b5f] shadow-sm" : "text-[#68797a]"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function EventTimeline({
  events,
  entityById,
  isAdmin,
  saving,
  onReview,
}: {
  events: HistoricalEvent[];
  entityById: Map<string, GraphEntity>;
  isAdmin: boolean;
  saving: boolean;
  onReview: (
    event: HistoricalEvent,
    status: ReviewStatus,
    note: string,
  ) => Promise<void>;
}) {
  if (!events.length) {
    return (
      <BusinessEmptyState
        icon={CalendarDays}
        title="暂无时间事件"
        description="当前筛选条件下没有事件记录。"
        className="min-h-64"
      />
    );
  }
  return (
    <ol className="relative ml-3 border-l border-[#9bb7b4] bg-white py-2">
      {events.map((item) => {
        const place = item.place_entity_id
          ? entityById.get(item.place_entity_id)
          : null;
        const participants = item.participant_entity_ids
          .map((id) => entityById.get(id)?.canonical_name ?? id)
          .join("、");
        return (
          <li
            key={item.id}
            id={`graph-event-${item.id}`}
            className="relative grid gap-3 border-b px-5 py-5 last:border-b-0 md:grid-cols-[150px_minmax(0,1fr)_180px]"
          >
            <span className="absolute top-7 -left-[5px] size-2.5 rounded-full border-2 border-white bg-[#39777a]" />
            <div>
              <div className="font-mono text-sm font-semibold text-[#225f64]">
                {item.start_time ?? "年代待考"}
              </div>
              <div className="mt-1 text-xs text-[#68797a]">
                {item.time_certainty === "exact"
                  ? "明确纪年"
                  : item.time_certainty === "approximate"
                    ? "约略纪年"
                    : "时间待考"}
              </div>
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-semibold">{item.title}</h2>
                <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] text-amber-800">
                  {reviewLabels[item.review_status]}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-[#536568]">
                {item.summary ?? "暂无事件摘要。"}
              </p>
              <div className="mt-2 text-xs leading-5 text-[#68797a]">
                {participants && <p>人物：{participants}</p>}
                {place && <p>地点：{place.canonical_name}</p>}
                {item.release_id && (
                  <p className="break-all">知识版本编号：{item.release_id}</p>
                )}
              </div>
            </div>
            <div className="text-xs">
              <p className="font-medium text-[#536568]">
                {item.evidence_ids.length} 条资料出处
              </p>
              <div className="mt-1 space-y-1">
                {item.evidence_ids.map((evidenceId, index) => (
                  <a
                    key={evidenceId}
                    href={`/api/knowledge-search/evidence/${encodeURIComponent(evidenceId)}`}
                    target="_blank"
                    rel="noreferrer"
                    className="block text-[#24676c] hover:underline"
                  >
                    查看出处 {index + 1}
                  </a>
                ))}
              </div>
              {place && (
                <Link
                  href="/workspace/map"
                  className="mt-2 inline-flex items-center gap-1 text-[#24676c] hover:underline"
                >
                  <MapPinned className="size-3" /> 地图查看
                </Link>
              )}
              {isAdmin && (
                <GraphReviewControls
                  status={item.review_status}
                  hasEvidence={item.evidence_ids.length > 0}
                  disabled={saving}
                  onReview={(status, note) => onReview(item, status, note)}
                />
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function EntitySelect({
  value,
  entities,
  onChange,
}: {
  value: string;
  entities: GraphEntity[];
  onChange: (value: string) => void;
}) {
  return (
    <select
      required
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="field"
    >
      <option value="">选择实体</option>
      {entities.map((item) => (
        <option key={item.id} value={item.id}>
          {item.canonical_name}（{item.entity_type}）
        </option>
      ))}
    </select>
  );
}

function AdminForm({
  title,
  onSubmit,
  saving,
  children,
}: {
  title: string;
  onSubmit: () => Promise<void>;
  saving: boolean;
  children: React.ReactNode;
}) {
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void onSubmit();
      }}
      className="space-y-3 border-l border-[#d8e2df] pl-4"
    >
      <h3 className="text-sm font-medium">{title}</h3>
      {children}
      <button
        type="submit"
        disabled={saving}
        className="inline-flex h-9 items-center gap-1.5 rounded-md bg-[#296a6f] px-3 text-sm text-white disabled:opacity-40"
      >
        <Plus className="size-4" />
        保存
      </button>
    </form>
  );
}
