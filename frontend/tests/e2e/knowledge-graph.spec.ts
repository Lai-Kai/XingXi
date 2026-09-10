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

test("loads peripheral relationships and evidence beyond the local catalog", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  const outerPlace = {
    ...entities[2]!,
    id: "place-outer",
    canonical_name: "越地",
    evidence_ids: ["ev-outer"],
  };
  const networkEntities = [...entities, outerPlace];
  const networkRelations = [
    ...relations,
    {
      ...relations[1]!,
      id: "rel-outer",
      subject_id: "place-mudu",
      object_id: "person-far",
      relation_type: "related_to",
      evidence_ids: ["ev-outer"],
    },
    {
      ...relations[1]!,
      id: "rel-third",
      subject_id: "person-far",
      object_id: "place-outer",
      evidence_ids: ["ev-outer"],
    },
  ];
  const requests: URL[] = [];
  let failDepthChange = true;
  await page.route("**/api/entities*", (route) =>
    route.fulfill({ json: entities.slice(0, 3) }),
  );
  await page.route("**/api/knowledge-graph/relations*", (route) =>
    route.fulfill({ json: relations.slice(0, 2) }),
  );
  await page.route("**/api/knowledge-graph/query*", (route) => {
    const url = new URL(route.request().url());
    requests.push(url);
    const subject = url.searchParams.get("entity");
    const center = networkEntities.find(
      (entity) => entity.id === subject || entity.canonical_name === subject,
    )!;
    const depth = Number(url.searchParams.get("max_depth"));
    if (depth === 3 && failDepthChange) {
      return route.fulfill({
        status: 503,
        json: { detail: "关系网暂时不可用" },
      });
    }
    const ids = new Set([center.id]);
    const edges = new Map<string, (typeof networkRelations)[number]>();
    for (let layer = 0; layer < depth; layer++) {
      const frontier = new Set(ids);
      for (const relation of networkRelations) {
        if (
          !frontier.has(relation.subject_id) &&
          !frontier.has(relation.object_id)
        )
          continue;
        edges.set(relation.id, relation);
        ids.add(relation.subject_id);
        ids.add(relation.object_id);
      }
    }
    return route.fulfill({
      json: {
        query: subject,
        status: "supported",
        message: "",
        candidates: [center],
        nodes: networkEntities.filter((entity) => ids.has(entity.id)),
        edges: [...edges.values()],
        evidence: [
          ...evidence,
          {
            ...evidence[0],
            evidence_id: "ev-outer",
            document_title: "外围关系文献",
          },
        ],
        truncated: false,
        max_depth: depth,
        max_nodes: 200,
        release_id: "release-1",
      },
    });
  });

  await page.goto("/workspace/knowledge-graph");
  await expect(
    page.getByRole("button", { name: "两层关系网", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.locator('.react-flow__node[data-id="person-far"]'),
  ).toBeVisible();
  await expect(
    page.locator('.react-flow__node[data-id="place-outer"]'),
  ).toHaveCount(0);
  const peripheral = page.locator("#graph-relation-rel-outer");
  await peripheral.getByRole("button", { name: "查看资料出处" }).click();
  await expect(
    peripheral.getByText("外围关系文献", { exact: false }),
  ).toBeVisible();

  await page.getByRole("button", { name: "三层关系网", exact: true }).click();
  await expect(
    page.getByText("关系网暂时不可用", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "两层关系网", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.locator('.react-flow__node[data-id="person-far"]'),
  ).toBeVisible();
  failDepthChange = false;
  await page.getByRole("button", { name: "三层关系网", exact: true }).click();
  await expect(
    page.locator('.react-flow__node[data-id="place-outer"]'),
  ).toBeVisible();
  expect(
    requests.some(
      (url) =>
        url.searchParams.get("max_depth") === "3" &&
        url.searchParams.get("release_id") === "release-1",
    ),
  ).toBe(true);

  await page.getByRole("button", { name: "直接关系", exact: true }).click();
  await expect(
    page.locator('.react-flow__node[data-id="person-far"]'),
  ).toHaveCount(0);
  await expect(page.locator("#graph-relation-rel-outer")).toHaveCount(0);

  await page.getByRole("button", { name: "两层关系网", exact: true }).click();
  await peripheral.getByRole("button", { name: "顾况", exact: true }).click();
  await expect(page.getByRole("heading", { name: "顾况" })).toBeVisible();
  await expect(
    page.locator('.react-flow__node[data-id="place-outer"]'),
  ).toBeVisible();
  expect(
    requests.some(
      (url) =>
        url.searchParams.get("entity") === "person-far" &&
        url.searchParams.get("max_depth") === "2" &&
        url.searchParams.get("release_id") === "release-1",
    ),
  ).toBe(true);
});
