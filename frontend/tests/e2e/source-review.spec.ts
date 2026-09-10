import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const documentId = "document-review-1";
const fileId = "source-file-review-1";
const jobId = "ingestion-job-review-1";

async function mockReviewAPI(page: Page) {
  mockLangGraphAPI(page);
  await page.route("**/api/source-documents/upload/limits", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        max_files: 10,
        max_file_size: 50_000_000,
        max_total_size: 100_000_000,
        allowed_extensions: [".png"],
      }),
    }),
  );
  await page.route("**/api/source-documents", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: documentId,
          title: "木渎小志",
          edition: "民国整理本",
          source_institution: "测试资料室",
        },
      ]),
    }),
  );
  await page.route(`**/api/source-documents/${documentId}/files`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success_count: 1,
        failure_count: 0,
        items: [
          {
            filename: "mudu.png",
            status: "uploaded",
            file: {
              id: fileId,
              document_id: documentId,
              object_key: "objects/mudu.png",
              original_filename: "mudu.png",
              mime_type: "image/png",
              size: 128,
              sha256: "a".repeat(64),
              duplicate_of_file_id: null,
              version_of_file_id: null,
              uploaded_by: "admin-1",
              uploaded_at: "2026-07-21T00:00:00Z",
            },
            ingestion_job: {
              id: jobId,
              document_id: documentId,
              source_file_id: fileId,
              status: "awaiting_review",
              current_step: "review",
              progress_percent: 70,
              steps: [],
              error_code: null,
              error_message: null,
              owner_worker_id: null,
              lease_expires_at: null,
              version: 9,
              event_sequence: 9,
              created_at: "2026-07-21T00:00:00Z",
              updated_at: "2026-07-21T00:00:00Z",
              completed_at: null,
            },
          },
        ],
      }),
    }),
  );
  await page.route(
    `**/api/source-documents/${documentId}/files/${fileId}/chunks`,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "chunk-set-1",
            source_file_id: fileId,
            policy: { split_version: "structure-v1" },
            generated_at: "2026-07-21T00:00:00Z",
          },
        ]),
      }),
  );
  await page.route(
    `**/api/source-documents/${documentId}/files/${fileId}/review/queue**`,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          document_id: documentId,
          source_file_id: fileId,
          chunk_set_id: "chunk-set-1",
          split_version: "structure-v1",
          pages: [
            {
              id: "cleaned-page-1",
              page_number: 1,
              folio_label: "一",
              generation_number: 1,
              raw_text: "卷一\n後臺沿河。",
              clean_text: "卷一\n后台沿河。",
              review_status: "pending",
              ocr_confidence: 0.96,
              rotation_degrees: 0,
              cleaning_change_count: 1,
            },
          ],
          chunks: [
            {
              id: "chunk-1",
              chunk_index: 0,
              volume: "卷一",
              item: "目一",
              raw_text: "後臺沿河。",
              clean_text: "后台沿河。",
              page_start: 1,
              page_end: 1,
              cleaned_page_ids: ["cleaned-page-1"],
              review_status: "pending",
            },
          ],
        }),
      }),
  );
  await page.route(
    `**/api/source-documents/${documentId}/files/${fileId}/review/history**`,
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "[]",
      }),
  );
  await page.route("**/api/knowledge-releases/state", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        active_release_id: "release-1",
        active_version: "v1",
        state_version: 1,
        updated_by: "admin-1",
        updated_at: "2026-07-21T00:00:00Z",
      }),
    }),
  );
  await page.route("**/api/knowledge-releases", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "release-1",
          version_number: 1,
          version: "v1",
          release_notes: "首批复核文献",
          scope: "public",
          status: "active",
          failure_code: null,
          failure_message: null,
          preparation_attempts: 1,
          ready_at: "2026-07-21T00:00:00Z",
          activated_at: "2026-07-21T00:00:00Z",
          manifest_sha256: "b".repeat(64),
          items: [
            {
              ordinal: 0,
              document_id: documentId,
              source_file_id: fileId,
              chunk_set_id: "chunk-set-1",
              chunk_id: "chunk-1",
              content_sha256: "c".repeat(64),
              cleaned_page_ids: ["cleaned-page-1"],
            },
          ],
          created_by: "admin-1",
          created_at: "2026-07-21T00:00:00Z",
        },
      ]),
    }),
  );
}

async function openReviewDialog(page: Page) {
  await page.goto("/workspace/library");
  await page.getByRole("button", { name: "上传文献" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "mudu.png",
    mimeType: "image/png",
    buffer: Buffer.from("not-a-real-png"),
  });
  await page.getByRole("button", { name: "开始上传" }).click();
  await expect(page.getByText("mudu.png").first()).toBeVisible();
  await page.getByRole("button", { name: "关闭" }).click();
  await page.getByRole("button", { name: "复核" }).click();
  await expect(
    page.getByRole("dialog", { name: "文本人工复核" }),
  ).toBeVisible();
}

test("review workspace shows traceable raw and clean text", async ({
  page,
}, testInfo) => {
  await mockReviewAPI(page);
  await openReviewDialog(page);

  const dialog = page.getByRole("dialog", { name: "文本人工复核" });
  await expect(dialog.getByText("後臺沿河。", { exact: false })).toBeVisible();
  await expect(dialog.getByText("后台沿河。", { exact: false })).toBeVisible();
  await expect(dialog.getByText("OCR 96%")).toBeVisible();
  await expect(dialog.getByText("叶码 一")).toBeVisible();
  await expect(dialog.getByRole("link", { name: "打开原件" })).toHaveAttribute(
    "href",
    `/api/source-documents/${documentId}/files/${fileId}/content`,
  );
  await expect(dialog.getByRole("button", { name: "通过" })).toBeEnabled();
  await expect(dialog.getByRole("button", { name: "退回" })).toBeEnabled();
  await expect(dialog.getByRole("button", { name: "标记争议" })).toBeEnabled();
  await page.screenshot({
    path: testInfo.outputPath("stage17-review-desktop.png"),
    fullPage: true,
  });
});

test("review workspace remains usable on a narrow viewport", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockReviewAPI(page);
  await openReviewDialog(page);

  const dialog = page.getByRole("dialog", { name: "文本人工复核" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "按页复核" })).toBeVisible();
  await expect(dialog.getByText("原始文本")).toBeVisible();
  await expect(dialog.getByText("清洗文本")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("stage17-review-mobile.png"),
    fullPage: true,
  });
});

test("selected reviewed documents open the knowledge release workspace", async ({
  page,
}, testInfo) => {
  await mockReviewAPI(page);
  await page.goto("/workspace/library");
  await page.getByRole("button", { name: "上传文献" }).click();
  await page.locator('input[type="file"]').setInputFiles({
    name: "mudu.png",
    mimeType: "image/png",
    buffer: Buffer.from("not-a-real-png"),
  });
  await page.getByRole("button", { name: "开始上传" }).click();
  await page.getByRole("button", { name: "关闭" }).click();
  await page.getByRole("checkbox", { name: "选择 mudu.png" }).check();
  await page.getByRole("button", { name: "知识版本 (1)" }).click();

  const dialog = page.getByRole("dialog", { name: "知识版本" });
  await expect(dialog.getByText("当前版本 v1")).toBeVisible();
  await expect(
    dialog.getByText("首批复核文献", { exact: false }),
  ).toBeVisible();
  await dialog.getByPlaceholder("填写本次发布说明").fill("补充木渎方志校订");
  await expect(
    dialog.getByRole("button", { name: "发布并启用" }),
  ).toBeEnabled();
  await page.screenshot({
    path: testInfo.outputPath("stage18-release-desktop.png"),
    fullPage: true,
  });
});
