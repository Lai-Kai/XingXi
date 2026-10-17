import type { Page } from "@playwright/test";

import { mockLangGraphAPI } from "../e2e/utils/mock-api";

import { evaluationCases, evaluationFixture } from "./agent-evaluations";
import { mockAdminGraph } from "./ui-admin-graph";

export const adminSource = {
  id: "admin-source",
  title: "木渎方志校勘样本（软件测试）",
  edition: "测试整理本",
  source_institution: "测试馆藏",
  source_type: "gazetteer",
  source_type_label: null,
  source_level: "C",
  holder: "软件测试",
  status: "registered",
  created_at: "2026-10-15T01:00:00Z",
  updated_at: "2026-10-15T01:00:00Z",
};
export const adminFile = {
  id: "admin-file",
  document_id: adminSource.id,
  object_key: "fixture/page.png",
  original_filename: "校勘样本.png",
  mime_type: "image/png",
  size: 20480,
  sha256: "a".repeat(64),
  duplicate_of_file_id: null,
  version_of_file_id: null,
  uploaded_by: "admin",
  uploaded_at: "2026-10-15T01:00:00Z",
};
export const adminJob = {
  id: "admin-job",
  document_id: adminSource.id,
  source_file_id: adminFile.id,
  status: "awaiting_review",
  current_step: "review",
  progress_percent: 70,
  steps: [],
  error_code: null,
  error_message: null,
  version: 1,
  event_sequence: 1,
  created_at: "2026-10-15T01:00:00Z",
  updated_at: "2026-10-15T01:00:00Z",
  completed_at: null,
};
const pageTarget = {
  id: "clean-page-1",
  page_number: 1,
  folio_label: "一上",
  generation_number: 1,
  raw_text: "軟件測試原文。\n木瀆沿河而居。",
  clean_text: "软件测试原文。\n木渎沿河而居。",
  review_status: "pending",
  ocr_confidence: null,
  rotation_degrees: 0,
  cleaning_change_count: 2,
};
const chunkTarget = {
  id: "chunk-1",
  chunk_index: 0,
  volume: "卷一",
  item: "水系",
  raw_text: pageTarget.raw_text,
  clean_text: pageTarget.clean_text,
  page_start: 1,
  page_end: 1,
  cleaned_page_ids: [pageTarget.id],
  review_status: "pending",
};
const version = {
  id: "chunkset-1",
  source_file_id: adminFile.id,
  policy: { split_version: "test-split-v1" },
  generated_at: "2026-10-15T02:00:00Z",
};
const tasks = [
  {
    id: "admin-task",
    thread_id: null,
    context_mode: "fresh_thread_per_run" as const,
    title: "每日方志线索研读",
    prompt: "整理新收录方志中的地名线索",
    schedule_type: "cron" as const,
    schedule_spec: { cron: "0 9 * * *" },
    timezone: "Asia/Shanghai",
    status: "enabled" as const,
    next_run_at: "2026-10-16T01:00:00Z",
    last_run_at: "2026-10-15T01:00:00Z",
    last_run_id: "scheduled-run-1",
    last_error: null,
    run_count: 3,
    created_at: "2026-10-14T01:00:00Z",
    updated_at: "2026-10-15T01:00:00Z",
  },
];
const scan =
  '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="640"><rect width="480" height="640" fill="#f4efdf"/><rect x="32" y="28" width="416" height="580" fill="none" stroke="#7b7466"/><text x="64" y="90" font-size="22" fill="#514b42">软件测试影印 · 非真实古籍</text><text x="85" y="160" font-size="20" fill="#514b42">軟件測試原文。</text><text x="85" y="210" font-size="20" fill="#514b42">木瀆沿河而居。</text></svg>';

export async function mockAdmin(page: Page) {
  await page.route("**/api/**", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "软件测试：此服务暂不可用" },
    }),
  );
  const graph = await mockAdminGraph(page, true);
  mockLangGraphAPI(page, { scheduledTasks: tasks });
  const state = {
    decisions: [] as Record<string, unknown>[],
    publishes: [] as Record<string, unknown>[],
    reviews: [] as Record<string, unknown>[],
    reviewFailure: false,
    publishFailure: false,
    qualityFailure: false,
    sourceStatus: "pending",
    chunkStatus: "pending",
    releaseVersion: 1,
  };
  const feedback = {
    feedback_id: "feedback-1",
    thread_id: "history-thread",
    run_id: "answer-run",
    user_id: "reader",
    rating: -1,
    comment: "请核对这条方志引文的卷次与出处。（软件测试）",
    category: "citation_error",
    status: "submitted",
    review_note: null,
    created_at: "2026-10-15T02:30:00Z",
  };
  await page.route("**/api/source-documents/library/page?**", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            source: adminSource,
            files: [{ file: adminFile, ingestion_job: adminJob }],
          },
        ],
        total: 1,
        limit: 10,
        offset: 0,
      },
    }),
  );
  await page.route("**/api/source-documents", (route) =>
    route.fulfill({ json: [adminSource] }),
  );
  await page.route("**/api/research-projects", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route(
    `**/api/source-documents/${adminSource.id}/files/${adminFile.id}/**`,
    async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/content"))
        return route.fulfill({ contentType: "image/svg+xml", body: scan });
      if (path.endsWith("/chunks")) return route.fulfill({ json: [version] });
      if (path.includes("/review/queue"))
        return route.fulfill({
          json: {
            document_id: adminSource.id,
            source_file_id: adminFile.id,
            chunk_set_id: version.id,
            split_version: version.policy.split_version,
            pages: [{ ...pageTarget, review_status: state.sourceStatus }],
            chunks: [{ ...chunkTarget, review_status: state.chunkStatus }],
          },
        });
      if (path.endsWith("/review/decisions")) {
        const body = route.request().postDataJSON();
        state.decisions.push(body);
        if (state.reviewFailure)
          return route.fulfill({
            status: 409,
            json: { detail: "测试：版本已改变，请重新核对" },
          });
        for (const decision of body.items ?? []) {
          if (decision.target_type === "page")
            state.sourceStatus = decision.decision;
          else state.chunkStatus = decision.decision;
        }
        return route.fulfill({ json: [] });
      }
      if (path.includes("/review/history")) return route.fulfill({ json: [] });
      if (path.endsWith("/review/finalize"))
        return route.fulfill({ json: { status: "completed" } });
      return route.fulfill({ json: {} });
    },
  );
  await page.route("**/api/knowledge-releases**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const release = {
      id: `release-${state.releaseVersion}`,
      version: `v${state.releaseVersion}`,
      version_number: state.releaseVersion,
      release_notes: "软件测试知识版本",
      scope: "public",
      status: "active",
      failure_code: null,
      failure_message: null,
      preparation_attempts: 1,
      manifest_sha256: "b".repeat(64),
      items: [],
      created_at: "2026-10-15T01:00:00Z",
      created_by: "admin",
      ready_at: null,
      activated_at: null,
    };
    if (path.endsWith("/state"))
      return route.fulfill({
        json: {
          active_release_id: release.id,
          active_version: release.version,
          state_version: state.releaseVersion,
          updated_by: "admin",
          updated_at: "2026-10-15T01:00:00Z",
        },
      });
    if (route.request().method() === "POST") {
      state.publishes.push(route.request().postDataJSON());
      if (state.sourceStatus !== "reviewed" || state.chunkStatus !== "reviewed")
        return route.fulfill({
          status: 409,
          json: { detail: "测试：复核尚未完成" },
        });
      if (state.publishFailure)
        return route.fulfill({
          status: 409,
          json: { detail: "测试：生效版本已更新" },
        });
      state.releaseVersion++;
      return route.fulfill({ json: release });
    }
    return route.fulfill({ json: [release] });
  });
  await page.route("**/api/threads/feedback/quality-queue?**", (route) =>
    route.fulfill({
      json: { items: [feedback], total: 1, limit: 20, offset: 0 },
    }),
  );
  await page.route("**/api/threads/feedback/*/review", (route) => {
    const body = route.request().postDataJSON();
    state.reviews.push(body);
    if (state.qualityFailure)
      return route.fulfill({ status: 500, json: { detail: "保存失败" } });
    return route.fulfill({ json: { ...feedback, ...body } });
  });
  await page.route("**/api/entities?**", (route) =>
    route.fulfill({ json: graph.nodes }),
  );
  await page.route("**/api/knowledge-graph/relations?**", (route) =>
    route.fulfill({ json: graph.edges }),
  );
  await page.route("**/api/knowledge-graph/events?**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/knowledge-graph/geo?**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/operations/evaluations/**", (route) => {
    const url = new URL(route.request().url());
    const batch = evaluationFixture();
    if (url.pathname.endsWith("/catalog"))
      return route.fulfill({
        json: {
          available: true,
          version: "test-v1",
          execution_mode: "replay",
          cases: evaluationCases,
        },
      });
    if (url.pathname.endsWith("/executions"))
      return route.fulfill({ json: [batch] });
    if (url.pathname.endsWith(batch.id)) return route.fulfill({ json: batch });
    return route.fulfill({ json: [] });
  });
  await page.route("**/api/operations/dashboard?**", (route) =>
    route.fulfill({
      json: {
        answer_accuracy_rate: 0.875,
        citation_rate: 0.9,
        refusal_compliance_rate: null,
        user_satisfaction_rate: 0.8,
        answer_count: 40,
        unanswered_count: 3,
        map_point_click_count: 26,
        manual_correction_count: 4,
        three_dimensional_load_success_rate: null,
        hot_entities: [
          { entity_id: "mudu", name: "木渎古镇", views: 18 },
          { entity_id: "lingyan", name: "灵岩山", views: 9 },
        ],
      },
    }),
  );
  for (const path of ["tasks?**", "corrections", "asset-versions"])
    await page.route(`**/api/operations/${path}`, (route) =>
      route.fulfill({ json: [] }),
    );
  return state;
}
