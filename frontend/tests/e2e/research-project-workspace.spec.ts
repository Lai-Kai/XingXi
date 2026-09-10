import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test("a research project becomes a scoped document workspace", async ({
  page,
}, testInfo) => {
  mockLangGraphAPI(page);
  const project = {
    id: "project-1",
    name: "吴郡人物关系研究",
    archived: 0,
    document_count: 0,
    created_at: "2026-08-15T09:00:00+08:00",
    updated_at: "2026-08-15T09:00:00+08:00",
  };
  const source = {
    id: "source-1",
    title: "吴郡图经续记",
    edition: "明抄本",
    source_institution: "测试文献馆",
    source_type: "gazetteer",
    source_type_label: null,
    source_level: "A",
    holder: "测试文献馆",
    status: "registered",
    created_at: "2026-08-15T09:00:00+08:00",
    updated_at: "2026-08-15T09:00:00+08:00",
  };
  let documents: Array<Record<string, unknown>> = [];
  let records: Array<Record<string, unknown>> = [];

  await page.route(/\/api\/research-projects$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ ...project, document_count: documents.length }]),
    }),
  );
  await page.route(/\/api\/research-projects\/project-1$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...project, document_count: documents.length }),
    }),
  );
  await page.route(
    /\/api\/research-projects\/project-1\/documents$/,
    async (route) => {
      if (route.request().method() === "POST") {
        documents = [
          {
            ...source,
            added_at: "2026-08-15T10:00:00+08:00",
          },
        ];
        return route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            project_id: project.id,
            document_id: source.id,
          }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(documents),
      });
    },
  );
  await page.route(
    /\/api\/research-projects\/project-1\/records$/,
    async (route) => {
      if (route.request().method() === "POST") {
        const body = route.request().postDataJSON() as {
          kind: string;
          content: string;
        };
        const record = {
          id: "record-1",
          project_id: project.id,
          kind: body.kind,
          content: body.content,
          created_by: "researcher-1",
          created_at: "2026-08-15T10:30:00+08:00",
          updated_at: "2026-08-15T10:30:00+08:00",
        };
        records = [record];
        return route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(record),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(records),
      });
    },
  );
  await page.route("**/api/source-documents/page?*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [source],
        total: 1,
        limit: 100,
        offset: 0,
      }),
    }),
  );
  await page.route("**/api/knowledge-search/structured", async (route) => {
    const request = route.request().postDataJSON() as {
      filters?: { document_ids?: string[] };
    };
    expect(request.filters?.document_ids).toEqual([source.id]);
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        query: "范仲淹",
        release_id: "release-1",
        filters: request.filters,
        page_size: 8,
        returned_count: 1,
        candidate_count: 1,
        has_more: false,
        next_cursor: null,
        degraded: false,
        evidence_status: "supported",
        message: "已检索到项目文献中的证据",
        alias_expansion: null,
        hits: [
          {
            release_id: "release-1",
            chunk_id: "chunk-1",
            fused_score: 1,
            channels: ["fulltext"],
            citation: {
              evidence_id: "evidence-1",
              document_id: source.id,
              document_title: source.title,
              edition: source.edition,
              volume: "卷一",
              section: "人物",
              page_start: 12,
              page_end: 12,
              quote: "范文正公尝游于此。",
              source_level: "A",
              review_status: "reviewed",
            },
          },
        ],
      }),
    });
  });

  await page.goto("/workspace/projects");
  const projectLink = page.getByRole("link", { name: project.name });
  await expect(projectLink).toBeVisible();
  await projectLink.click();
  await expect(page).toHaveURL(/\/workspace\/projects\/project-1$/);
  await expect(page.getByText("项目还没有文献")).toBeVisible();

  await page.getByRole("button", { name: "添加文献" }).click();
  await page.getByRole("button", { name: "添加", exact: true }).click();
  await expect(page.getByText("吴郡图经续记").first()).toBeVisible();
  await page.getByRole("button", { name: "完成" }).click();

  await page
    .getByPlaceholder("记录接下来需要查证的问题")
    .fill("范仲淹与木渎有什么关系？");
  await page.getByRole("button", { name: "保存研究问题" }).click();
  await expect(page.getByText("范仲淹与木渎有什么关系？")).toBeVisible();

  await page.getByPlaceholder("输入人物、地点、事件或史料原文").fill("范仲淹");
  await page.getByRole("button", { name: "检索", exact: true }).click();
  await expect(page.getByText("范文正公尝游于此。")).toBeVisible();
  await expect(page.getByRole("link", { name: "查看关联证据" })).toBeVisible();

  const agentLink = page.getByRole("link", { name: "用项目文献研究" });
  await expect(agentLink).toHaveAttribute("href", /project_id=project-1/);

  await page.screenshot({
    path: testInfo.outputPath("project-workspace-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: testInfo.outputPath("project-workspace-mobile.png"),
    fullPage: true,
  });
});
