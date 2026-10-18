import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

async function mockLibrary(page: Page, reviewed = true) {
  mockLangGraphAPI(page);
  let source = {
    id: "source-library-1",
    title: "测试方志",
    edition: null,
    source_institution: "测试资料室",
    source_type: "gazetteer",
    source_type_label: null,
    source_level: "U",
    holder: "测试资料室",
    status: "registered",
    created_at: "2026-10-17T00:00:00Z",
    updated_at: "2026-10-17T00:00:00Z",
  };
  let job = {
    id: "job-1",
    status: "failed",
    current_step: "chunk",
    steps: [],
    error_message: "too many SQL variables",
  };
  let pageReviewed = reviewed;
  let chunkReviewed = reviewed;
  let libraryReads = 0;
  let saved: Record<string, unknown> | null = null;
  const prefix = "**/api/source-documents/source-library-1/files/file-1";
  await page.route("**/api/source-documents/library/page**", (route) => {
    libraryReads += 1;
    return route.fulfill({
      json: {
        total: 1,
        limit: 10,
        offset: 0,
        items: [
          {
            source,
            files: [
              {
                file: {
                  id: "file-1",
                  document_id: source.id,
                  original_filename: "library.txt",
                  size: 64,
                  uploaded_at: "2026-10-17T00:00:00Z",
                },
                ingestion_job: job,
                chunk_set_id: "set-1",
                review_status:
                  pageReviewed && chunkReviewed ? "reviewed" : "pending",
              },
            ],
          },
        ],
      },
    });
  });
  await page.route(
    "**/api/source-documents/source-library-1",
    async (route) => {
      saved = route.request().postDataJSON() as Record<string, unknown>;
      source = { ...source, ...saved };
      await route.fulfill({ json: source });
    },
  );
  await page.route(`${prefix}/generate-graph`, (route) => {
    job = { ...job, status: "pending", error_message: "" };
    return route.fulfill({ json: job });
  });
  await page.route(`${prefix}/ingestion-jobs/job-1`, (route) =>
    route.fulfill({ json: job }),
  );
  await page.route(`${prefix}/chunks`, (route) =>
    route.fulfill({ json: [{ id: "set-1", policy: { split_version: "v1" } }] }),
  );
  await page.route(`${prefix}/review/queue**`, (route) =>
    route.fulfill({
      json: {
        chunk_set_id: "set-1",
        split_version: "v1",
        pages: [
          {
            id: "page-1",
            page_number: 1,
            generation_number: 1,
            raw_text: "木渎方志。",
            clean_text: "木渎方志。",
            review_status: pageReviewed ? "reviewed" : "pending",
            cleaning_change_count: 0,
          },
        ],
        chunks: [
          {
            id: "chunk-1",
            chunk_index: 0,
            raw_text: "木渎方志。",
            clean_text: "木渎方志。",
            page_start: 1,
            page_end: 1,
            cleaned_page_ids: ["page-1"],
            review_status: chunkReviewed ? "reviewed" : "pending",
          },
        ],
      },
    }),
  );
  await page.route(`${prefix}/review/history**`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(`${prefix}/review/decisions`, (route) => {
    const { items } = route.request().postDataJSON() as {
      items: { target_type: string }[];
    };
    for (const item of items) {
      if (item.target_type === "page") pageReviewed = true;
      else chunkReviewed = true;
    }
    return route.fulfill({ json: [] });
  });
  await page.route(`${prefix}/review/finalize`, (route) => {
    job = {
      ...job,
      status: "pending",
      current_step: "index",
      error_message: "",
    };
    return route.fulfill({ json: job });
  });
  return { saved: () => saved, reads: () => libraryReads };
}

for (const width of [1440, 390]) {
  test(`library preserves review status and edits an unknown edition at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const state = await mockLibrary(page);
    await page.goto("/workspace/library");
    await expect(page.getByText("文本复核", { exact: true })).toHaveCount(1);
    await expect(page.getByText("已复核", { exact: true })).toHaveCount(1);
    await expect(
      page.getByRole("status").filter({ hasText: /^(处理成功|处理失败)$/ }),
    ).toHaveCount(1);
    await page.getByRole("button", { name: "编辑资料信息" }).click();
    const dialog = page.getByRole("dialog", { name: "编辑资料信息" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByLabel("版本 / 年代")).toHaveValue("");
    await dialog.getByLabel("资料名称").fill("测试方志校订资料");
    await dialog.getByRole("button", { name: "保存修改" }).click();
    await expect(dialog).toHaveCount(0);
    expect(state.saved()?.edition).toBeNull();
    await page.reload();
    await expect(page.getByText("测试方志校订资料 · 版本未详")).toHaveCount(1);
    await expect(page.getByText("已复核", { exact: true })).toHaveCount(1);
    await page.getByRole("button", { name: /^(重试处理|生成图谱)$/ }).click();
    await expect(page.getByText("等待处理", { exact: true })).toHaveCount(1);
    await expect(page.getByText("已复核", { exact: true })).toHaveCount(1);
    expect(errors).toEqual([]);
  });
}

test("review decisions refresh library state and finalization keeps the server's pending index status", async ({
  page,
}) => {
  const state = await mockLibrary(page, false);
  await page.goto("/workspace/library");
  await page.getByRole("button", { name: "复核", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "文本人工复核" });
  await dialog.getByRole("button", { name: "通过", exact: true }).click();
  await expect.poll(state.reads).toBeGreaterThan(1);
  await dialog.getByRole("button", { name: "按片段复核" }).click();
  await dialog.getByRole("button", { name: "通过", exact: true }).click();
  await expect(page.getByText("已复核", { exact: true })).toHaveCount(1);
  await dialog.getByRole("button", { name: "完成复核" }).click();
  await expect(page.getByText("等待处理", { exact: true })).toHaveCount(1);
  await expect(page.getByText("已完成", { exact: true })).toHaveCount(0);
});
