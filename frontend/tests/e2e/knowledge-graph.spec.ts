import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const entities = [
  {
    id: "person-li",
    canonical_name: "李明",
    entity_type: "person",
    dynasty: null,
    extant_status: null,
    summary: "木渎地方人物",
    review_status: "reviewed",
    release_id: null,
    evidence_ids: ["ev-family"] as string[],
  },
  {
    id: "person-wang",
    canonical_name: "王芳",
    entity_type: "person",
    dynasty: null,
    extant_status: null,
    summary: "李明的姐姐",
    review_status: "reviewed",
    release_id: null,
    evidence_ids: ["ev-family"],
  },
  {
    id: "place-mudu",
    canonical_name: "木渎古镇",
    entity_type: "place",
    dynasty: "qing",
    extant_status: "extant",
    summary: "吴地历史街区",
    review_status: "reviewed",
    release_id: null,
    evidence_ids: ["ev-residence"] as string[],
  },
  {
    id: "person-far",
    canonical_name: "顾况",
    entity_type: "person",
    dynasty: "唐",
    extant_status: null,
    summary: "另一个有出处的主体",
    review_status: "reviewed",
    release_id: null,
    evidence_ids: ["ev-family"] as string[],
  },
];

const relations = [
  {
    id: "rel-family",
    subject_id: "person-li",
    relation_type: "sibling_of",
    object_id: "person-wang",
    start_time: null,
    end_time: null,
    confidence: 0.95,
    evidence_ids: ["ev-family"],
    is_inferred: false,
    review_status: "reviewed",
    release_id: null,
  },
  {
    id: "rel-residence",
    subject_id: "person-li",
    relation_type: "lived_in",
    object_id: "place-mudu",
    start_time: "1920",
    end_time: "1940",
    confidence: 0.82,
    evidence_ids: ["ev-residence"],
    is_inferred: false,
    review_status: "reviewed",
    release_id: null,
  },
  {
    id: "rel-visit",
    subject_id: "person-wang",
    relation_type: "visited",
    object_id: "place-mudu",
    start_time: "1935",
    end_time: null,
    confidence: 0.76,
    evidence_ids: [] as string[],
    is_inferred: true,
    review_status: "pending",
    release_id: null,
  },
];

const evidence = [
  {
    evidence_id: "ev-family",
    document_id: "doc-family",
    chunk_id: "chunk-family",
    source_level: "reviewed",
    review_status: "reviewed",
    document_title: "木渎人物谱",
    edition: "民国抄本",
    volume: "卷二",
    section: "家族关系",
    page_start: 18,
    page_end: 18,
  },
  {
    evidence_id: "ev-residence",
    document_id: "doc-residence",
    chunk_id: "chunk-residence",
    source_level: "catalog",
    review_status: "reviewed",
    document_title: "木渎镇志",
    edition: "地方志",
    volume: "卷八",
    section: "人物",
    page_start: 42,
    page_end: 43,
  },
];

function graphFor(entityId: string) {
  const visibleRelations = relations.filter(
    (relation) =>
      relation.subject_id === entityId || relation.object_id === entityId,
  );
  const nodeIds = new Set([entityId]);
  visibleRelations.forEach((relation) => {
    nodeIds.add(relation.subject_id);
    nodeIds.add(relation.object_id);
  });
  return {
    query: entityId,
    status: "supported",
    message: "Knowledge graph relationships found.",
    candidates: entities.filter((entity) => entity.id === entityId),
    nodes: entities.filter((entity) => nodeIds.has(entity.id)),
    edges: visibleRelations,
    evidence: evidence.filter((item) =>
      visibleRelations.some((relation) =>
        relation.evidence_ids.includes(item.evidence_id),
      ),
    ),
    truncated: false,
  };
}

test("explores one-hop relationships from a clicked subject", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  await page.route("**/api/entities*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(entities),
    }),
  );
  await page.route("**/api/knowledge-graph/relations*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(relations),
    }),
  );
  await page.route("**/api/knowledge-graph/events*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    }),
  );
  await page.route("**/api/knowledge-graph/geo*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    }),
  );
  await page.route("**/api/knowledge-graph/query*", (route) => {
    const entityId = new URL(route.request().url()).searchParams.get("entity");
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(graphFor(entityId ?? "")),
    });
  });

  await page.goto("/workspace/knowledge-graph");
  await expect(page.getByRole("heading", { name: "知识图谱" })).toBeVisible();
  await expect(page.getByText("主体索引")).toHaveCount(0);

  await page.locator(".react-flow__node").filter({ hasText: "李明" }).click();
  await expect(page.getByText("当前探索中心")).toBeVisible();
  await expect(page.getByRole("heading", { name: "李明" })).toBeVisible();
  const relationPanel = page.locator("aside");
  await expect(relationPanel.getByText("兄弟姐妹")).toBeVisible();
  await expect(relationPanel.getByText("居住于")).toBeVisible();

  await page.getByRole("button", { name: "人物关系" }).click();
  await expect(relationPanel.getByText("兄弟姐妹")).toBeVisible();
  await expect(relationPanel.getByText("居住于")).toHaveCount(0);
  await page.getByRole("button", { name: "全部关系" }).click();
  await expect(relationPanel.getByText("居住于")).toBeVisible();

  await relationPanel.getByRole("button", { name: "王芳" }).click();
  await expect(page.getByRole("heading", { name: "王芳" })).toBeVisible();
  await expect(relationPanel.getByText("游览/到访")).toBeVisible();

  await page.getByRole("button", { name: "查看资料出处" }).first().click();
  await expect(page.getByText("木渎人物谱")).toBeVisible();
});
