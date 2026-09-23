import { expect, test, type Page } from "@playwright/test";

import type { OverviewNode, OverviewPage } from "../../src/core/knowledge-graph/overview";
import type { GraphRelation } from "../../src/core/knowledge-graph/types";

import { mockLangGraphAPI } from "./utils/mock-api";

async function mockOverview(page: Page, admin = false, truncated = false) {
  mockLangGraphAPI(page);
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "reader", email: "reader@test.local", system_role: admin ? "admin" : "user", needs_setup: false } }));
  const nodes: OverviewNode[] = [
    ["kangxi", "康熙帝", "person", "清"], ["dengwei", "邓尉山", "place", "清"],
    ["gukuang", "顾况", "person", "唐"], ["mudu", "木渎", "place", "唐"],
    ["building", "古建筑", "building", "清"],
  ].map(([id, name, kind, dynasty], index) => ({ id: id!, canonical_name: name!, entity_type: kind as OverviewNode["entity_type"], dynasty: dynasty!, review_status: "reviewed", evidence_ids: ["ev"], summary: "测试史料", release_id: "release", extant_status: null, has_relations: index < 4, component_id: index < 2 ? "kangxi" : index < 4 ? "gukuang" : null }));
  const edges: GraphRelation[] = [
    { id: "kd", subject_id: "kangxi", object_id: "dengwei", relation_type: "visited", review_status: "reviewed" },
    { id: "gm", subject_id: "gukuang", object_id: "mudu", relation_type: "lived_in", review_status: admin ? "pending" : "reviewed" },
  ].map(edge => ({ ...edge, start_time: "史料纪年", end_time: null, confidence: .9, evidence_ids: ["ev"], is_inferred: false, release_id: "release" })) as GraphRelation[];
  const state = { localDelay: 0, requests: [] as string[] };
  await page.route("**/api/knowledge-graph/overview?*", async route => {
    const url = new URL(route.request().url());
    state.requests.push(url.toString());
    let visible = edges.filter(edge => (!url.searchParams.get("relation_type") || edge.relation_type === url.searchParams.get("relation_type")) && (!url.searchParams.get("review_status") || edge.review_status === url.searchParams.get("review_status")));
    if (url.searchParams.get("scope") === "people") visible = [];
    const components = visible.map(edge => ({ id: edge.subject_id, label: `${nodes.find(n => n.id === edge.subject_id)!.canonical_name}、${nodes.find(n => n.id === edge.object_id)!.canonical_name}`, total_nodes: 2, total_edges: 1 }));
    const center = url.searchParams.get("center");
    const component = url.searchParams.get("component_id");
    if (center) { visible = visible.filter(edge => [edge.subject_id, edge.object_id].includes(center)); if (state.localDelay) await new Promise(resolve => setTimeout(resolve, state.localDelay)); }
    if (component) visible = visible.filter(edge => edge.subject_id === component);
    const total = visible.length;
    const limited = truncated && !center && !component && total > 1;
    if (limited) visible = url.searchParams.has("cursor") ? visible.slice(1) : visible.slice(0, 1);
    const ids = new Set(visible.flatMap(edge => [edge.subject_id, edge.object_id]));
    const response: OverviewPage = { release_id: "release", nodes: nodes.filter(node => ids.has(node.id)), edges: visible, total_nodes: total * 2, total_edges: total, returned_nodes: ids.size, returned_edges: visible.length, truncated: limited && !url.searchParams.has("cursor"), next_cursor: limited && !url.searchParams.has("cursor") ? "second" : null, components, evidence: [{ evidence_id: "ev", document_title: "测试方志", page_start: 1, page_end: 1 }] };
    await route.fulfill({ json: response });
  });
  await page.route("**/api/knowledge-graph/directory?*", route => {
    const params = new URL(route.request().url()).searchParams;
    const rows = nodes.filter(node => (!params.get("name") || node.canonical_name.includes(params.get("name")!)) && (!params.get("entity_type") || node.entity_type === params.get("entity_type")) && (!params.get("dynasty") || node.dynasty === params.get("dynasty")));
    return route.fulfill({ json: { release_id: "release", nodes: rows, edges: [], total_nodes: rows.length, total_edges: 2, returned_nodes: rows.length, returned_edges: 0, truncated: false, next_cursor: null, components: [], evidence: [] } });
  });
  return state;
}

test("discovers two groups, selects without replacing the graph, and restores overview", async ({ page }) => {
  await mockOverview(page);
  await page.goto("/workspace/knowledge-graph");
  const graph = page.getByTestId("global-graph");
  await expect(graph.locator(".react-flow__node")).toHaveCount(4);
  await expect(page.getByRole("button", { name: /顾况、木渎/ })).toBeVisible();
  await graph.locator('[data-id="gukuang"]').click();
  await expect(graph).toHaveAttribute("data-mode", "overview");
  await expect(graph.locator(".react-flow__edge")).toHaveCount(2);
  await page.getByRole("complementary", { name: "选中详情" }).getByRole("button", { name: "以此为中心探索" }).click();
  await expect(graph).toHaveAttribute("data-mode", "local");
  await expect(graph.locator(".react-flow__edge")).toHaveCount(1);
  await page.getByRole("button", { name: "返回全局总览" }).click();
  await expect(graph.locator(".react-flow__edge")).toHaveCount(2);
  await expect(page.getByRole("complementary", { name: "选中详情" })).toContainText("顾况");
  await expect(page.getByLabel("关系范围")).toHaveValue("all");
});

test("directory discovers places and isolated buildings; search locates without clearing the graph", async ({ page }) => {
  await mockOverview(page);
  await page.goto("/workspace/knowledge-graph");
  await page.getByLabel("主体类型", { exact: true }).selectOption("building");
  const directory = page.getByRole("region", { name: "主体目录" });
  await expect(directory.getByRole("button", { name: /古建筑/ })).toBeVisible();
  await expect(directory).toContainText("暂无关系");
  await page.getByLabel("主体类型", { exact: true }).selectOption("place");
  await expect(directory.getByRole("button", { name: /木渎/ })).toBeVisible();
  await page.getByLabel("搜索定位主体").fill("木渎");
  await directory.getByRole("button", { name: /木渎/ }).click();
  await expect(page.getByTestId("global-graph").locator(".react-flow__node")).toHaveCount(4);
  await expect(page.getByTestId("global-graph").locator('[data-id="mudu"]')).toHaveClass(/selected/);
});

test("filters synchronize counts and ordinary users have no privileged data or controls", async ({ page }) => {
  await mockOverview(page);
  await page.goto("/workspace/knowledge-graph");
  await expect(page.getByLabel("审核状态", { exact: true })).toHaveCount(0);
  await expect(page.getByText("待审人物", { exact: true })).toHaveCount(0);
  await page.getByLabel("关系类型", { exact: true }).selectOption("visited");
  await expect(page.getByText("已加载 2/2 个主体、1/1 条关系", { exact: true })).toBeVisible();
  await page.getByLabel("关系范围", { exact: true }).selectOption("people");
  await expect(page.getByText("已加载 0/0 个主体、0/0 条关系", { exact: true })).toBeVisible();
});

test("admin review filters and return preserve the global filters", async ({ page }) => {
  await mockOverview(page, true);
  await page.goto("/workspace/knowledge-graph");
  await page.getByLabel("审核状态", { exact: true }).selectOption("pending");
  await expect(page.getByText("已加载 2/2 个主体、1/1 条关系", { exact: true })).toBeVisible();
  await page.getByTestId("global-graph").locator('[data-id="gukuang"]').click();
  await page.getByRole("complementary", { name: "选中详情" }).getByRole("button", { name: "以此为中心探索" }).click();
  await page.getByLabel("审核状态", { exact: true }).selectOption("reviewed");
  await page.getByRole("button", { name: "返回全局总览" }).click();
  await expect(page.getByLabel("审核状态", { exact: true })).toHaveValue("pending");
  await expect(page.getByTestId("global-graph").locator('[data-id="gukuang"]')).toBeVisible();
});

test("truncation shows real totals and every group remains discoverable", async ({ page }) => {
  await mockOverview(page, false, true);
  await page.goto("/workspace/knowledge-graph");
  await expect(page.getByText("已加载 2/4 个主体、1/2 条关系", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /顾况、木渎/ })).toBeVisible();
  await page.getByRole("button", { name: "加载更多关系" }).click();
  await expect(page.getByText("已加载 4/4 个主体、2/2 条关系", { exact: true })).toBeVisible();
  await expect(page.getByTestId("global-graph").locator(".react-flow__edge")).toHaveCount(2);
});

test("late local requests cannot replace the global graph", async ({ page }) => {
  const state = await mockOverview(page);
  state.localDelay = 500;
  await page.goto("/workspace/knowledge-graph");
  await page.getByTestId("global-graph").locator('[data-id="gukuang"]').click();
  await page.getByRole("complementary", { name: "选中详情" }).getByRole("button", { name: "以此为中心探索" }).click();
  await page.getByRole("button", { name: "返回全局总览" }).click();
  await page.waitForTimeout(650);
  await expect(page.getByTestId("global-graph")).toHaveAttribute("data-mode", "overview");
  await expect(page.getByTestId("global-graph").locator(".react-flow__edge")).toHaveCount(2);
});

test("mobile provides a relation list and bottom-sheet details", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockOverview(page);
  await page.goto("/workspace/knowledge-graph");
  await page.getByRole("button", { name: "关系列表", exact: true }).click();
  await expect(page.getByLabel("移动端关系列表")).toContainText("康熙帝 → 邓尉山");
  await expect(page.getByLabel("移动端关系列表")).toContainText("顾况 → 木渎");
  await page.getByRole("button", { name: "图谱", exact: true }).click();
  await page.getByTestId("global-graph").locator('[data-id="gukuang"]').click();
  await expect(page.getByRole("dialog")).toContainText("主体与关系详情");
  await expect(page.getByRole("dialog")).toContainText("可靠程度 90%");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
