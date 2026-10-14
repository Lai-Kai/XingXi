import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test("automatic evaluations retain failures, reviews, exports and cancelled reruns", async ({
  page,
}, testInfo) => {
  mockLangGraphAPI(page);
  const testCase = {
    id: "grounded-pro",
    title: "引用核对",
    question: "测试桥在哪里？",
    mode: "pro",
    version: 1,
    scenario: "grounded",
    review_rubric: "仅合成资料",
  };
  const original = {
    id: "batch-original",
    execution_mode: "replay",
    status: "completed",
    total: 1,
    passed: 0,
    created_at: "2026-09-26T00:00:00Z",
    started_at: null,
    finished_at: null,
    parent_id: null,
    cancel_requested: false,
    error_message: null,
    environment: { suite_version: "xingxi-core-v1" },
    counts: { failed: 1 },
    reviews: [] as Array<Record<string, string>>,
    results: [
      {
        attempt_id: "attempt-1",
        case_id: testCase.id,
        case: testCase,
        status: "completed",
        verdict: "failed",
        answer: "示例错误回答",
        agent_run_id: "real-run-id",
        elapsed_ms: 125,
        checks: [
          {
            key: "citations_valid",
            label: "引用必须存在",
            status: "failed",
            expected: "真实证据",
            actual: "错误引用",
          },
        ],
        events: [
          {
            seq: 1,
            at: "2026-09-26T00:00:00Z",
            type: "tool_call",
            name: "search_sources",
            args: { query: "测试桥" },
          },
        ],
        evidence: [],
      },
    ],
  };
  let batches = [original];
  await page.route("**/api/operations/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const reply = (body: unknown) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (path.endsWith("/catalog"))
      return reply({
        available: true,
        version: "xingxi-core-v1",
        cases: [testCase],
      });
    if (path.endsWith("/executions") && route.request().method() === "POST")
      return reply(original);
    if (path.endsWith("/executions")) return reply(batches);
    if (path.endsWith("/export"))
      return route.fulfill({
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Content-Disposition": "attachment; filename=report.json",
        },
        body: JSON.stringify(original),
      });
    if (path.endsWith("/reviews")) {
      const body = route.request().postDataJSON() as {
        case_id: string;
        decision: string;
        note: string;
      };
      original.reviews.push({
        id: "review-1",
        created_at: original.created_at,
        actor_id: "admin",
        ...body,
      });
      return reply(original);
    }
    if (path.endsWith("/rerun")) {
      const rerun = {
        ...original,
        id: "batch-rerun",
        parent_id: original.id,
        status: "running",
        counts: {},
        reviews: [],
        results: [],
      };
      batches = [rerun, original] as typeof batches;
      return reply(rerun);
    }
    if (path.endsWith("/cancel")) {
      batches[0]!.status = "cancelled";
      return reply(batches[0]);
    }
    if (path.includes("/executions/"))
      return reply(batches.find((batch) => path.endsWith(batch.id)));
    if (path.endsWith("/dashboard"))
      return reply({
        answer_accuracy_rate: null,
        citation_rate: null,
        refusal_compliance_rate: null,
        user_satisfaction_rate: null,
        answer_count: 0,
        unanswered_count: 0,
        map_point_click_count: 0,
        manual_correction_count: 0,
        three_dimensional_load_success_rate: null,
        hot_entities: [],
      });
    return reply([]);
  });
  await page.goto("/workspace/operations");
  await page.getByRole("button", { name: "回归评测", exact: true }).click();
  await page.getByRole("link", { name: "打开 Agent 评测" }).click();
  await expect(page).toHaveURL(/\/workspace\/evaluations$/);
  const panel = page.getByRole("region", {
    name: "Agent 自动评测",
    exact: true,
  });
  await panel.getByRole("button", { name: "引用核对 · 查看轨迹" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("示例错误回答")).toBeVisible();
  await dialog.getByText("引用必须存在", { exact: true }).click();
  await expect(dialog.getByText("错误引用", { exact: true })).toBeVisible();
  await expect(dialog.getByText("real-run-id", { exact: true })).toBeVisible();
  await dialog.getByLabel("复核意见").fill("检查后仍然不通过");
  await dialog.getByRole("button", { name: "保存复核" }).click();
  await expect(
    dialog.getByText("检查后仍然不通过", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  const download = page.waitForEvent("download");
  await panel.getByRole("button", { name: "JSON", exact: true }).click();
  expect((await download).suggestedFilename()).toContain("batch-original.json");
  await page.screenshot({
    path: testInfo.outputPath("agent-evaluation-detail.png"),
    fullPage: true,
  });
  await panel.getByRole("button", { name: "重跑未通过项" }).click();
  await panel.getByRole("button", { name: "取消评测" }).click();
  await expect(
    panel.getByRole("heading", { name: "已取消", exact: true }),
  ).toBeVisible();
  await panel.getByRole("button", { name: "查看原批次及失败记录" }).click();
  await panel.getByRole("button", { name: "引用核对 · 查看轨迹" }).click();
  await expect(dialog.getByText("示例错误回答")).toBeVisible();
  await page.reload();
  await panel.getByRole("button", { name: "查看原批次及失败记录" }).click();
  await panel.getByRole("button", { name: "引用核对 · 查看轨迹" }).click();
  await expect(
    dialog.getByText("检查后仍然不通过", { exact: true }),
  ).toBeVisible();
});
