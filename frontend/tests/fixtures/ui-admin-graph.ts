import type { Page } from "@playwright/test";

import type {
  OverviewNode,
  OverviewPage,
} from "../../src/core/knowledge-graph/overview";
import type { GraphRelation } from "../../src/core/knowledge-graph/types";
import { mockLangGraphAPI } from "../e2e/utils/mock-api";

export async function mockAdminGraph(
  page: Page,
  admin = false,
  truncated = false,
) {
  mockLangGraphAPI(page);
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "reader",
        email: "reader@test.local",
        system_role: admin ? "admin" : "user",
        needs_setup: false,
      },
    }),
  );
  const nodes: OverviewNode[] = [
    ["kangxi", "康熙帝", "person", "清"],
    ["dengwei", "邓尉山", "place", "清"],
    ["gukuang", "顾况", "person", "唐"],
    ["mudu", "木渎", "place", "唐"],
    ["building", "古建筑", "building", "清"],
  ].map(([id, name, kind, dynasty], index) => ({
    id: id!,
    canonical_name: name!,
    entity_type: kind as OverviewNode["entity_type"],
    dynasty: dynasty!,
    review_status: "reviewed",
    evidence_ids: ["ev"],
    summary: "测试史料",
    release_id: "release",
    extant_status: null,
    has_relations: index < 4,
    component_id: index < 2 ? "kangxi" : index < 4 ? "gukuang" : null,
  }));
  const edges: GraphRelation[] = [
    {
      id: "kd",
      subject_id: "kangxi",
      object_id: "dengwei",
      relation_type: "visited",
      review_status: "reviewed",
    },
    {
      id: "gm",
      subject_id: "gukuang",
      object_id: "mudu",
      relation_type: "lived_in",
      review_status: admin ? "pending" : "reviewed",
    },
  ].map((edge) => ({
    ...edge,
    start_time: "史料纪年",
    end_time: null,
    confidence: 0.9,
    evidence_ids: ["ev"],
    is_inferred: false,
    release_id: "release",
  })) as GraphRelation[];
  const state = { localDelay: 0, requests: [] as string[] };
  await page.route("**/api/knowledge-graph/overview?*", async (route) => {
    const url = new URL(route.request().url());
    state.requests.push(url.toString());
    let visible = edges.filter(
      (edge) =>
        (!url.searchParams.get("relation_type") ||
          edge.relation_type === url.searchParams.get("relation_type")) &&
        (!url.searchParams.get("review_status") ||
          edge.review_status === url.searchParams.get("review_status")),
    );
    if (url.searchParams.get("scope") === "people") visible = [];
    const components = visible.map((edge) => ({
      id: edge.subject_id,
      label: `${nodes.find((n) => n.id === edge.subject_id)!.canonical_name}、${nodes.find((n) => n.id === edge.object_id)!.canonical_name}`,
      total_nodes: 2,
      total_edges: 1,
    }));
    const center = url.searchParams.get("center");
    const component = url.searchParams.get("component_id");
    if (center) {
      visible = visible.filter((edge) =>
        [edge.subject_id, edge.object_id].includes(center),
      );
      if (state.localDelay)
        await new Promise((resolve) => setTimeout(resolve, state.localDelay));
    }
    if (component)
      visible = visible.filter((edge) => edge.subject_id === component);
    const total = visible.length;
    const limited = truncated && !center && !component && total > 1;
    if (limited)
      visible = url.searchParams.has("cursor")
        ? visible.slice(1)
        : visible.slice(0, 1);
    const ids = new Set(
      visible.flatMap((edge) => [edge.subject_id, edge.object_id]),
    );
    const response: OverviewPage = {
      release_id: "release",
      nodes: nodes.filter((node) => ids.has(node.id)),
      edges: visible,
      total_nodes: total * 2,
      total_edges: total,
      returned_nodes: ids.size,
      returned_edges: visible.length,
      truncated: limited && !url.searchParams.has("cursor"),
      next_cursor: limited && !url.searchParams.has("cursor") ? "second" : null,
      components,
      evidence: [
        {
          evidence_id: "ev",
          document_title: "测试方志",
          page_start: 1,
          page_end: 1,
        },
      ],
    };
    await route.fulfill({ json: response });
  });
  await page.route("**/api/knowledge-graph/directory?*", (route) => {
    const params = new URL(route.request().url()).searchParams;
    const rows = nodes.filter(
      (node) =>
        (!params.get("name") ||
          node.canonical_name.includes(params.get("name")!)) &&
        (!params.get("entity_type") ||
          node.entity_type === params.get("entity_type")) &&
        (!params.get("dynasty") || node.dynasty === params.get("dynasty")),
    );
    return route.fulfill({
      json: {
        release_id: "release",
        nodes: rows,
        edges: [],
        total_nodes: rows.length,
        total_edges: 2,
        returned_nodes: rows.length,
        returned_edges: 0,
        truncated: false,
        next_cursor: null,
        components: [],
        evidence: [],
      },
    });
  });
  return { ...state, nodes, edges };
}
