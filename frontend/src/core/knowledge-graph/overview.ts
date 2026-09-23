import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

import type { GraphEntity, GraphRelation, ReviewStatus } from "./types";

export type OverviewNode = GraphEntity & {
  has_relations?: boolean;
  component_id?: string | null;
};
export type OverviewPage = {
  release_id: string | null;
  nodes: OverviewNode[];
  edges: GraphRelation[];
  total_nodes: number;
  total_edges: number;
  returned_nodes: number;
  returned_edges: number;
  truncated: boolean;
  next_cursor: string | null;
  components: Array<{
    id: string;
    label: string;
    total_nodes: number;
    total_edges: number;
  }>;
  evidence: Array<{
    evidence_id: string;
    document_title: string;
    page_start: number | null;
    page_end: number | null;
  }>;
};
export type OverviewOptions = {
  scope?: "all" | "people";
  relation_type?: string;
  review_status?: ReviewStatus;
  component_id?: string;
  center?: string;
  release_id?: string;
  name?: string;
  entity_type?: string;
  dynasty?: string;
  cursor?: string;
  max_nodes?: number;
  max_edges?: number;
};

export async function fetchOverview(
  options: OverviewOptions,
  signal?: AbortSignal,
  directory = false,
): Promise<OverviewPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(options)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const response = await fetch(
    `${getBackendBaseURL()}/api/knowledge-graph/${directory ? "directory" : "overview"}?${params}`,
    { credentials: "include", signal, cache: "no-store" },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(
      typeof error?.detail === "string"
        ? error.detail
        : "图谱加载失败，请重试。",
    );
  }
  return response.json();
}

export function mergeOverview(
  previous: OverviewPage,
  next: OverviewPage,
): OverviewPage {
  if (previous.release_id !== next.release_id)
    throw new Error("知识版本已切换，请重新加载总览。");
  const nodes = [
    ...new Map(
      [...previous.nodes, ...next.nodes].map((node) => [node.id, node]),
    ).values(),
  ];
  const edges = [
    ...new Map(
      [...previous.edges, ...next.edges].map((edge) => [edge.id, edge]),
    ).values(),
  ];
  return {
    ...next,
    nodes,
    edges,
    returned_nodes: nodes.length,
    returned_edges: edges.length,
    evidence: [
      ...new Map(
        [...previous.evidence, ...next.evidence].map((item) => [
          item.evidence_id,
          item,
        ]),
      ).values(),
    ],
  };
}

/** A packed component grid has no privileged center or ego-graph rings. */
export function overviewPositions(
  nodes: GraphEntity[],
  edges: GraphRelation[],
) {
  const adjacency = new Map(nodes.map((node) => [node.id, new Set<string>()]));
  for (const edge of edges) {
    adjacency.get(edge.subject_id)?.add(edge.object_id);
    adjacency.get(edge.object_id)?.add(edge.subject_id);
  }
  const positions = new Map<string, { x: number; y: number }>();
  const visited = new Set<string>();
  let top = 0;
  let left = 0;
  let rowHeight = 0;
  for (const node of [...nodes].sort((a, b) => a.id.localeCompare(b.id))) {
    if (visited.has(node.id) || !adjacency.get(node.id)?.size) continue;
    const queue = [node.id];
    visited.add(node.id);
    for (const id of queue)
      for (const neighbor of adjacency.get(id) ?? []) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          queue.push(neighbor);
        }
      }
    const columns = Math.max(2, Math.ceil(Math.sqrt(queue.length)));
    const width = columns * 240;
    const height = Math.ceil(queue.length / columns) * 180;
    if (left && left + width > 1600) {
      top += rowHeight + 200;
      left = 0;
      rowHeight = 0;
    }
    queue.forEach((id, index) =>
      positions.set(id, {
        x: left + (index % columns) * 240,
        y: top + Math.floor(index / columns) * 180,
      }),
    );
    left += width + 240;
    rowHeight = Math.max(rowHeight, height);
  }
  return positions;
}
