"use client";

import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type ReactFlowInstance,
  type Viewport,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { GraphReviewControls } from "@/components/workspace/graph-review-controls";
import { reviewRelation } from "@/core/knowledge-graph/api";
import { layoutGraphEntities } from "@/core/knowledge-graph/layout";
import {
  fetchOverview,
  mergeOverview,
  overviewPositions,
  type OverviewNode,
  type OverviewOptions,
  type OverviewPage,
} from "@/core/knowledge-graph/overview";
import { reviewLabels } from "@/core/knowledge-graph/review";
import type { GraphRelation, ReviewStatus } from "@/core/knowledge-graph/types";

const types = {
  person: "人物",
  place: "地点",
  building: "建筑",
  family: "家族",
  work: "作品",
  event: "事件",
  waterway: "水系",
  bridge: "桥梁",
  garden: "园林",
  relic: "文物",
  organization: "机构",
};
const relations: Record<GraphRelation["relation_type"], string> = {
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
  died_at: "卒于",
  composed_at: "在此赋诗",
  mentioned_in_poetry: "诗文提及",
  documented_in: "出自文献",
};
const control = "rounded border bg-white px-3 py-2 text-sm disabled:opacity-50";

export function GraphOverview({ isAdmin }: { isAdmin: boolean }) {
  const [mode, setMode] = useState<"overview" | "local">("overview");
  const [scope, setScope] = useState<"all" | "people">("all");
  const [relationType, setRelationType] = useState("");
  const [review, setReview] = useState<ReviewStatus | "">("");
  const [component, setComponent] = useState("");
  const [center, setCenter] = useState<string | null>(null);
  const [overview, setOverview] = useState<OverviewPage | null>(null);
  const [local, setLocal] = useState<OverviewPage | null>(null);
  const [selected, setSelected] = useState<OverviewNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [directory, setDirectory] = useState<OverviewPage | null>(null);
  const [name, setName] = useState("");
  const [entityType, setEntityType] = useState("");
  const [dynasty, setDynasty] = useState("");
  const [listView, setListView] = useState(false);
  const [mobileDetail, setMobileDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [directoryError, setDirectoryError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [directoryBusy, setDirectoryBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [directoryRefresh, setDirectoryRefresh] = useState(0);
  const flow = useRef<ReactFlowInstance | null>(null);
  const viewport = useRef<Viewport | null>(null);
  const overviewSelection = useRef<{
    node: OverviewNode | null;
    edge: string | null;
  }>({ node: null, edge: null });
  const overviewFilters = useRef({ scope, relationType, review, component });
  const pendingLocation = useRef<OverviewNode | null>(null);
  const requests = useRef({ sequence: 0, abort: new AbortController() });
  const directoryRequest = useRef({
    sequence: 0,
    abort: new AbortController(),
  });
  const currentMode = useRef(mode);
  currentMode.current = mode;
  const filterKey = JSON.stringify([
    scope,
    relationType,
    review,
    component,
    isAdmin,
    refresh,
  ]);
  const loadedKey = useRef("");
  const data = mode === "overview" ? overview : local;
  const options: OverviewOptions = {
    scope,
    relation_type: relationType,
    review_status: review || undefined,
    component_id: mode === "overview" ? component : undefined,
    center: mode === "local" ? (center ?? undefined) : undefined,
  };
  const optionsRef = useRef(options);
  optionsRef.current = options;

  async function load(more = false) {
    requests.current.abort.abort();
    const abort = new AbortController();
    const sequence = ++requests.current.sequence;
    requests.current.abort = abort;
    const target = currentMode.current;
    const previous = target === "overview" ? overview : local;
    setBusy(true);
    setError(null);
    try {
      const next = await fetchOverview(
        {
          ...optionsRef.current,
          ...(more
            ? {
                cursor: previous?.next_cursor ?? undefined,
                release_id: previous?.release_id ?? undefined,
              }
            : target === "local"
              ? { release_id: overview?.release_id ?? undefined }
              : {}),
        },
        abort.signal,
      );
      if (
        sequence !== requests.current.sequence ||
        target !== currentMode.current
      )
        return;
      const value = more && previous ? mergeOverview(previous, next) : next;
      if (target === "overview") {
        setOverview(value);
        loadedKey.current = filterKey;
      } else setLocal(value);
      if (!more) {
        setSelected(
          (current) =>
            value.nodes.find(
              (n) => n.id === (pendingLocation.current?.id ?? current?.id),
            ) ?? null,
        );
        setSelectedEdge(null);
      }
    } catch (reason) {
      if (!abort.signal.aborted && sequence === requests.current.sequence)
        setError(reason instanceof Error ? reason.message : "加载失败");
    } finally {
      if (sequence === requests.current.sequence) setBusy(false);
    }
  }
  useEffect(() => {
    if (mode === "overview" && loadedKey.current === filterKey) {
      setBusy(false);
      return;
    }
    if (mode === "overview") setOverview(null);
    else setLocal(null);
    void load();
    return () => {
      requests.current.abort.abort();
      requests.current.sequence++;
    };
    // Request identity is explicitly bound to these inputs, not response state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, center, filterKey]);

  const directoryOptions = {
    scope,
    relation_type: relationType,
    review_status: review || undefined,
    name,
    entity_type: entityType,
    dynasty,
  };
  const directoryKey = JSON.stringify([
    directoryOptions,
    isAdmin,
    directoryRefresh,
    refresh,
  ]);
  async function loadDirectory(more = false) {
    directoryRequest.current.abort.abort();
    const abort = new AbortController();
    const sequence = ++directoryRequest.current.sequence;
    directoryRequest.current.abort = abort;
    setDirectoryBusy(true);
    setDirectoryError(null);
    try {
      const next = await fetchOverview(
        {
          ...directoryOptions,
          ...(more
            ? {
                cursor: directory?.next_cursor ?? undefined,
                release_id: directory?.release_id ?? undefined,
              }
            : {}),
        },
        abort.signal,
        true,
      );
      if (sequence === directoryRequest.current.sequence)
        setDirectory(more && directory ? mergeOverview(directory, next) : next);
    } catch (reason) {
      if (!abort.signal.aborted)
        setDirectoryError(
          reason instanceof Error ? reason.message : "主体目录加载失败",
        );
    } finally {
      if (sequence === directoryRequest.current.sequence)
        setDirectoryBusy(false);
    }
  }
  useEffect(() => {
    setDirectory(null);
    const timer = setTimeout(() => void loadDirectory(), 150);
    return () => {
      clearTimeout(timer);
      directoryRequest.current.abort.abort();
      directoryRequest.current.sequence++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [directoryKey]);

  function choose(node: OverviewNode) {
    setSelected(node);
    setSelectedEdge(null);
    setMobileDetail(true);
    if (mode === "overview") overviewSelection.current = { node, edge: null };
  }
  function explore() {
    if (!selected) return;
    viewport.current = flow.current?.getViewport() ?? viewport.current;
    overviewSelection.current = { node: selected, edge: selectedEdge };
    overviewFilters.current = { scope, relationType, review, component };
    requests.current.abort.abort();
    requests.current.sequence++;
    setMobileDetail(false);
    setCenter(selected.id);
    setMode("local");
  }
  function back() {
    requests.current.abort.abort();
    requests.current.sequence++;
    setError(null);
    setMode("overview");
    setSelected(overviewSelection.current.node);
    setSelectedEdge(overviewSelection.current.edge);
    if (mode === "local") {
      const saved = overviewFilters.current;
      setScope(saved.scope);
      setRelationType(saved.relationType);
      setReview(saved.review);
      setComponent(saved.component);
    }
  }
  function locate(node: OverviewNode) {
    choose(node);
    if (
      (!overview?.nodes.some((n) => n.id === node.id) || large) &&
      node.component_id
    ) {
      pendingLocation.current = node;
      viewport.current = null;
      setComponent(node.component_id);
    } else {
      const position = flow.current?.getNode(node.id)?.position;
      if (position)
        void flow.current?.setCenter(position.x + 85, position.y + 30, {
          zoom: 1,
          duration: 250,
        });
    }
  }
  const graphNodes = data?.nodes ?? [];
  const graphEdges = data?.edges ?? [];
  const large =
    mode === "overview" && !component && (data?.total_nodes ?? 0) > 250;
  const positions = useMemo(
    () =>
      mode === "overview"
        ? overviewPositions(graphNodes, graphEdges)
        : layoutGraphEntities(graphNodes, graphEdges, center),
    [graphNodes, graphEdges, mode, center],
  );
  const highlighted = new Set([
    selected?.id,
    ...graphEdges
      .filter(
        (e) =>
          selected?.id && [e.subject_id, e.object_id].includes(selected.id),
      )
      .flatMap((e) => [e.subject_id, e.object_id]),
  ]);
  const nodes = large
    ? (data?.components ?? []).map((group, index) => ({
        id: `component:${group.id}`,
        position: { x: (index % 4) * 280, y: Math.floor(index / 4) * 160 },
        data: {
          label: `${group.label}（${group.total_nodes} 主体 / ${group.total_edges} 关系）`,
        },
        style: { width: 220, minHeight: 70, background: "#edf7f4" },
      }))
    : graphNodes.map((node) => ({
        id: node.id,
        position: positions.get(node.id) ?? { x: 0, y: 0 },
        data: { label: `${node.canonical_name} · ${types[node.entity_type]}` },
        selected: selected?.id === node.id,
        style: {
          width: 170,
          minHeight: 55,
          background: node.entity_type === "person" ? "#fff8ed" : "#edf7f4",
          border: highlighted.has(node.id)
            ? "2px solid #24676c"
            : "1px solid #9baca8",
        },
      }));
  const edges = large
    ? []
    : graphEdges.map((edge) => ({
        id: edge.id,
        source: edge.subject_id,
        target: edge.object_id,
        label: relations[edge.relation_type],
        markerEnd: { type: MarkerType.ArrowClosed },
        selected: edge.id === selectedEdge,
        style: {
          stroke:
            selected?.id &&
            [edge.subject_id, edge.object_id].includes(selected.id)
              ? "#24676c"
              : "#9baca8",
          strokeWidth: edge.id === selectedEdge ? 3 : 1.5,
        },
      }));
  const byId = new Map(
    [
      ...(directory?.nodes ?? []),
      ...graphNodes,
      ...(selected ? [selected] : []),
    ].map((n) => [n.id, n]),
  );
  const relevant = selectedEdge
    ? graphEdges.filter((e) => e.id === selectedEdge)
    : graphEdges.filter(
        (e) => selected && [e.subject_id, e.object_id].includes(selected.id),
      );
  function edgeDetails(edge: GraphRelation) {
    return (
      <article
        key={edge.id}
        data-testid={`overview-relation-${edge.id}`}
        className="space-y-2 rounded border bg-white p-3 text-sm"
      >
        <p>
          {byId.get(edge.subject_id)?.canonical_name} →{" "}
          {byId.get(edge.object_id)?.canonical_name}
        </p>
        <p>
          {relations[edge.relation_type]} · {edge.start_time ?? "年代不详"}
          {edge.end_time ? ` — ${edge.end_time}` : ""}
        </p>
        <p>
          可靠程度 {Math.round(edge.confidence * 100)}% ·{" "}
          {reviewLabels[edge.review_status]}
          {edge.is_inferred ? " · 推断关系" : ""}
        </p>
        {edge.evidence_ids.map((id) => (
          <a
            key={id}
            className="block text-teal-800 underline"
            href={`/api/knowledge-search/evidence/${encodeURIComponent(id)}`}
            target="_blank"
            rel="noreferrer"
          >
            资料出处：
            {data?.evidence.find((e) => e.evidence_id === id)?.document_title ??
              id}
          </a>
        ))}
        {isAdmin && (
          <GraphReviewControls
            status={edge.review_status}
            hasEvidence={edge.evidence_ids.length > 0}
            disabled={saving}
            onReview={async (status, note) => {
              setSaving(true);
              try {
                await reviewRelation(edge.id, status, note, edge.review_status);
                setRefresh((v) => v + 1);
              } finally {
                setSaving(false);
              }
            }}
          />
        )}
      </article>
    );
  }
  const details = (
    <div className="space-y-3">
      {selected ? (
        <>
          <h3 className="font-semibold">{selected.canonical_name}</h3>
          <p className="text-sm">
            {types[selected.entity_type]} · {selected.dynasty ?? "朝代不详"} ·{" "}
            {reviewLabels[selected.review_status]}
          </p>
          <p className="text-sm">{selected.summary}</p>
          {mode === "overview" && (
            <button className={control} onClick={explore}>
              以此为中心探索
            </button>
          )}
          {selected.evidence_ids.map((id) => (
            <a
              key={id}
              className="block text-sm text-teal-800 underline"
              href={`/api/knowledge-search/evidence/${encodeURIComponent(id)}`}
              target="_blank"
              rel="noreferrer"
            >
              主体资料出处 {id}
            </a>
          ))}
          {relevant.length ? (
            relevant.map(edgeDetails)
          ) : (
            <p className="text-sm">当前已加载范围内暂无关系。</p>
          )}
          {data?.truncated && (
            <p className="text-sm">
              尚有关系未加载，可加载更多或进入局部探索查看。
            </p>
          )}
        </>
      ) : (
        <p className="text-sm text-slate-600">
          点击任意主体或关系查看详情；总览图将保持显示。
        </p>
      )}
    </div>
  );

  return (
    <section className="mt-4 space-y-4" aria-label="知识图谱浏览">
      <div
        className="flex flex-wrap items-center gap-2"
        role="group"
        aria-label="浏览模式"
      >
        <button
          className={control}
          aria-pressed={mode === "overview"}
          onClick={back}
        >
          {mode === "local" ? "返回全局总览" : "查看全局总览"}
        </button>
        <span className="font-medium">
          {mode === "overview" ? "全局总览" : "局部探索 · 一跳关系"}
        </span>
        {mode === "overview" && (
          <button className={control} disabled={!selected} onClick={explore}>
            局部探索
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <select
          className={control}
          aria-label="关系范围"
          value={scope}
          onChange={(e) => setScope(e.target.value as "all" | "people")}
        >
          <option value="all">全部关系类型</option>
          <option value="people">人物关系</option>
        </select>
        <select
          className={control}
          aria-label="关系类型"
          value={relationType}
          onChange={(e) => setRelationType(e.target.value)}
        >
          <option value="">不限关系类型</option>
          {Object.entries(relations).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        {isAdmin && (
          <select
            className={control}
            aria-label="审核状态"
            value={review}
            onChange={(e) => setReview(e.target.value as ReviewStatus | "")}
          >
            <option value="">全部可见审核状态</option>
            {Object.entries(reviewLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        )}
        <button
          className={control}
          onClick={() => {
            viewport.current = null;
            setRefresh((v) => v + 1);
          }}
        >
          重新加载
        </button>
      </div>
      {error && (
        <p role="alert" className="text-red-700">
          {error}{" "}
          <button className={control} onClick={() => void load()}>
            重试
          </button>
        </p>
      )}
      {busy && <p role="status">正在读取图谱…</p>}
      {data && (
        <>
          <p role="status">
            已加载 {data.nodes.length}/{data.total_nodes} 个主体、
            {data.edges.length}/{data.total_edges} 条关系
          </p>
          {data.truncated && (
            <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm">
              已达到本批加载上限，当前不是完整图谱。
              <button
                className={`${control} ml-2`}
                disabled={busy}
                onClick={() => void load(true)}
              >
                加载更多关系
              </button>{" "}
              或按下方关系群组浏览。
            </div>
          )}
          {!data.total_edges && (
            <p>当前知识版本和筛选下暂无可展示关系，请查看主体目录。</p>
          )}
        </>
      )}
      {mode === "overview" && (
        <div
          aria-label="关系群组"
          className="flex max-h-48 flex-wrap gap-2 overflow-y-auto"
        >
          <button
            className={control}
            aria-pressed={!component}
            onClick={() => setComponent("")}
          >
            所有关系群组
          </button>
          {data?.components.map((group) => (
            <button
              key={group.id}
              className={control}
              aria-pressed={component === group.id}
              onClick={() => {
                viewport.current = null;
                setComponent(group.id);
              }}
            >
              {group.label} · {group.total_nodes} 主体 / {group.total_edges}{" "}
              关系
            </button>
          ))}
        </div>
      )}
      {large && (
        <p className="text-sm">
          数据较多，画布显示所有关系群组概览；点击群组展开。
        </p>
      )}
      <div className="flex gap-2 lg:hidden">
        <button
          className={control}
          aria-pressed={!listView}
          onClick={() => setListView(false)}
        >
          图谱
        </button>
        <button
          className={control}
          aria-pressed={listView}
          onClick={() => setListView(true)}
        >
          关系列表
        </button>
      </div>
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          <div
            className={`${listView ? "hidden lg:block" : ""} h-[55vh] min-h-80 overflow-hidden rounded border bg-white`}
            data-testid="global-graph"
            data-mode={mode}
          >
            <ReactFlow<Node, Edge>
              key={`${mode}:${component}`}
              nodes={nodes}
              edges={edges}
              fitView={mode !== "overview" || !viewport.current}
              defaultViewport={
                mode === "overview"
                  ? (viewport.current ?? undefined)
                  : undefined
              }
              minZoom={0.03}
              maxZoom={2.5}
              nodesDraggable={false}
              nodesConnectable={false}
              onInit={(instance) => {
                flow.current = instance;
                if (mode === "overview" && viewport.current)
                  void instance.setViewport(viewport.current);
              }}
              onMoveEnd={(_event, value) => {
                if (currentMode.current === "overview")
                  viewport.current = value;
              }}
              onNodeClick={(_event, node) => {
                if (node.id.startsWith("component:")) {
                  setComponent(node.id.slice(10));
                  return;
                }
                const entity = byId.get(node.id);
                if (entity) choose(entity);
              }}
              onEdgeClick={(_event, edge) => {
                const relation = graphEdges.find((e) => e.id === edge.id);
                if (!relation) return;
                const node = byId.get(relation.subject_id);
                if (node) choose(node);
                setSelectedEdge(edge.id);
                overviewSelection.current = {
                  node: node ?? null,
                  edge: edge.id,
                };
              }}
            >
              <Background />
              <Controls showInteractive={false} />
              <MiniMap
                pannable
                zoomable
                position="top-right"
                ariaLabel="全局缩略图"
              />
            </ReactFlow>
          </div>
          <div
            className={`${listView ? "space-y-2 lg:hidden" : "hidden"}`}
            aria-label="移动端关系列表"
          >
            {graphEdges.map(edgeDetails)}
          </div>
          <div
            className="mt-2 flex flex-wrap items-center gap-3 text-xs"
            aria-label="图例"
          >
            <span>浅黄：人物</span>
            <span>浅绿：其他主体</span>
            <span>箭头：关系方向</span>
            <span>深绿：选中主体的一跳关系</span>
            <button
              className={control}
              onClick={() => void flow.current?.fitView({ padding: 0.2 })}
            >
              适配视图
            </button>
          </div>
        </div>
        <aside
          className="hidden max-h-[65vh] overflow-y-auto rounded border bg-white p-4 lg:block"
          aria-label="选中详情"
        >
          {details}
        </aside>
      </div>
      <Sheet
        open={
          mobileDetail &&
          typeof window !== "undefined" &&
          window.innerWidth < 1024
        }
        onOpenChange={setMobileDetail}
      >
        <SheetContent side="bottom" className="max-h-[75vh] overflow-y-auto">
          <SheetHeader>
            <SheetTitle>主体与关系详情</SheetTitle>
          </SheetHeader>
          <div className="p-4">{details}</div>
        </SheetContent>
      </Sheet>
      <section
        aria-label="主体目录"
        className="space-y-3 rounded border bg-white p-4"
      >
        <h3 className="font-semibold">主体目录</h3>
        <div className="flex flex-wrap gap-2">
          <input
            className={`${control} min-w-0`}
            aria-label="搜索定位主体"
            placeholder="搜索名称并定位主体"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <select
            className={control}
            aria-label="主体类型"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
          >
            <option value="">所有主体类型</option>
            {Object.entries(types).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
          <input
            className={`${control} w-32`}
            aria-label="朝代"
            placeholder="朝代"
            value={dynasty}
            onChange={(e) => setDynasty(e.target.value)}
          />
        </div>
        {directoryBusy && <p role="status">正在读取主体目录…</p>}
        {directoryError && (
          <p role="alert">
            {directoryError}
            <button
              className={control}
              onClick={() => setDirectoryRefresh((v) => v + 1)}
            >
              重试目录
            </button>
          </p>
        )}
        {directory && (
          <p className="text-sm">
            主体目录已加载 {directory.nodes.length}/{directory.total_nodes}{" "}
            个主体
          </p>
        )}
        {[true, false].map((connected) => (
          <div key={String(connected)}>
            <h4 className="mb-2 text-sm font-medium">
              {connected ? "有关联主体" : "暂无关系"}
            </h4>
            <div className="flex max-h-60 flex-wrap gap-2 overflow-y-auto">
              {directory?.nodes
                .filter((n) => Boolean(n.has_relations) === connected)
                .map((node) => (
                  <button
                    key={node.id}
                    className={control}
                    onClick={() => locate(node)}
                  >
                    {node.canonical_name} · {types[node.entity_type]} ·{" "}
                    {node.dynasty ?? "朝代不详"}
                  </button>
                ))}
            </div>
          </div>
        ))}
        {directory?.truncated && (
          <button
            className={control}
            disabled={directoryBusy}
            onClick={() => void loadDirectory(true)}
          >
            加载更多主体
          </button>
        )}
      </section>
    </section>
  );
}
