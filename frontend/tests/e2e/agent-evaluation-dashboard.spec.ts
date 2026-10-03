import { expect, test, type Page } from "@playwright/test";

import type { AgentEvaluation } from "../../src/core/operations/evaluations";
import {
  evaluationCases,
  evaluationFixture,
} from "../fixtures/agent-evaluations";

import { mockLangGraphAPI } from "./utils/mock-api";

async function mockEvaluations(page: Page, batches: AgentEvaluation[]) {
  mockLangGraphAPI(page);
  await page.route("**/api/operations/evaluations/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body: unknown = batches.find((item) => path.endsWith(item.id));
    if (path.endsWith("/catalog"))
      body = {
        available: true,
        version: "xingxi-core-v1",
        execution_mode: "replay",
        cases: evaluationCases,
      };
    if (path.endsWith("/executions"))
      body = batches.slice(
        Number(url.searchParams.get("offset") ?? 0),
        Number(url.searchParams.get("offset") ?? 0) + 20,
      );
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body ?? {}),
    });
  });
}

test("standalone navigation, real batch metrics, tooltips and combined filters", async ({
  page,
}, testInfo) => {
  await mockEvaluations(page, [
    evaluationFixture(),
    evaluationFixture("batch-previous", {
      created_at: "2026-09-30T00:00:00Z",
      pass_rate: 0.6,
    }),
  ]);
  await page.goto("/workspace/evaluations");
  await expect(
    page.getByRole("link", { name: "Agent 评测", exact: true }),
  ).toHaveAttribute("href", "/workspace/evaluations");
  await expect(
    page.getByRole("heading", { name: "星羲 Agent 自动评测" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "规则通过率", exact: true })
      .getByText("70.0%", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "平均用例耗时", exact: true })
      .getByText(/9 个有效样本/),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "执行错误数", exact: true })
      .getByText("1", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "测试记录", exact: true })
      .getByRole("row"),
  ).toHaveCount(11);
  await page
    .getByRole("region", { name: "历史批次图表" })
    .locator('rect[role="button"]')
    .first()
    .hover();
  await expect(page.getByRole("tooltip")).toContainText("60.0%");
  await page.getByRole("heading", { name: "星羲 Agent 自动评测" }).hover();
  await page.screenshot({
    path: testInfo.outputPath("evaluation-dashboard-desktop.png"),
    fullPage: true,
  });
  await page.getByLabel("场景筛选").selectOption("timeout");
  await page.getByLabel("执行模式筛选").selectOption("pro");
  await page.getByLabel("结果筛选").selectOption("passed");
  await page.getByLabel("搜索测试记录").fill("中断");
  const row = page.getByRole("row").filter({ hasText: "timeout-pro" });
  await expect(row.getByText("通过", { exact: true })).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "测试记录", exact: true })
      .getByRole("row"),
  ).toHaveCount(2);
  await row.getByRole("button", { name: /查看轨迹/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByText("运行已按用例预期中断。", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByText("batch-current-run-4", { exact: true }),
  ).toBeVisible();
  const timeline = await dialog.locator("ol > li").allTextContents();
  expect(timeline.findIndex((value) => value.includes("#2"))).toBeLessThan(
    timeline.findIndex((value) => value.includes("#3")),
  );
  await expect(
    dialog.locator("pre").filter({ hasText: '"query"' }),
  ).toContainText("测试桥");
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await page.getByLabel("搜索测试记录").fill("不存在的用例");
  await expect(page.getByText("没有符合筛选条件的测试记录。")).toBeVisible();
});

test("evidence locators and a responsive trajectory drawer remain readable on mobile", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockEvaluations(page, [evaluationFixture()]);
  await page.goto("/workspace/evaluations");
  await page
    .getByRole("button", { name: "有据回答与真实引用 · 查看轨迹" })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("测试资料（合成） · 第 1 页")).toBeVisible();
  await expect(dialog.getByText(/Chunk：synthetic-chunk-1/)).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  const bounds = await dialog.boundingBox();
  expect(bounds?.width).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: testInfo.outputPath("evaluation-trajectory-mobile.png"),
    fullPage: true,
  });
});

test("empty batches and missing durations never become fabricated metrics", async ({
  page,
}) => {
  await mockEvaluations(page, []);
  await page.goto("/workspace/evaluations");
  await expect(
    page.getByRole("heading", { name: "暂无自动评测记录" }),
  ).toBeVisible();
  await expect(page.getByText("100.0%", { exact: true })).not.toBeVisible();
  await expect(page.getByRole("table")).not.toBeVisible();
  const missing = evaluationFixture("batch-missing");
  missing.results.forEach((item) => {
    item.elapsed_ms = undefined;
  });
  await mockEvaluations(page, [missing]);
  await page.reload();
  await expect(
    page
      .getByRole("region", { name: "平均用例耗时", exact: true })
      .getByText("未采集", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "平均用例耗时", exact: true }),
  ).toContainText("0 个有效样本");
});

test("API failures remain errors and can recover without demo fallback", async ({
  page,
}) => {
  await mockEvaluations(page, [evaluationFixture()]);
  let failed = true;
  await page.route("**/api/operations/evaluations/executions?*", (route) =>
    failed
      ? route.fulfill({
          status: 403,
          contentType: "application/json",
          body: JSON.stringify({ detail: "评测记录读取失败" }),
        })
      : route.fallback(),
  );
  await page.goto("/workspace/evaluations");
  await expect(page.getByRole("alert")).toContainText("评测记录读取失败");
  await expect(page.getByRole("table")).not.toBeVisible();
  failed = false;
  await page.getByRole("button", { name: "重试读取" }).click();
  await expect(
    page.getByRole("region", { name: "规则通过率", exact: true }),
  ).toContainText("70.0%");
});

test("unfinished and empty-result batches cannot claim all passed", async ({
  page,
}) => {
  const batch = evaluationFixture("batch-running", {
    status: "running",
    passed: 10,
    pass_rate: 1,
  });
  await mockEvaluations(page, [batch]);
  await page.goto("/workspace/evaluations");
  await expect(
    page.getByRole("heading", { name: "执行中", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "全部通过", exact: true }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("region", { name: "规则通过率", exact: true }),
  ).toContainText("尚未完成");
  batch.status = "completed";
  batch.results = [];
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "结果记录不完整", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "规则通过率", exact: true }),
  ).toContainText("未采集");
});

test("governance readers can inspect records without execution or review controls", async ({
  page,
}) => {
  await mockEvaluations(page, [evaluationFixture()]);
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "reader",
        email: "reader@test.local",
        system_role: "user",
        business_role: "government",
        capabilities: ["governance:read"],
      }),
    }),
  );
  await page.goto("/workspace/evaluations");
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await expect(
    page.getByText(
      "可查看和导出记录；启动、取消、重跑与人工复核需要管理员权限。",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "运行核心 6 项" }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "重跑未通过项" }),
  ).not.toBeVisible();
  await expect(
    page.getByRole("button", { name: "JSON", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "有据回答与真实引用 · 查看轨迹" })
    .click();
  await expect(
    page.getByRole("dialog").getByLabel("复核意见"),
  ).not.toBeVisible();
});

test("users without governance access lose the navigation and see a permission state", async ({
  page,
}) => {
  await mockEvaluations(page, [evaluationFixture()]);
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "visitor",
        email: "visitor@test.local",
        system_role: "user",
        business_role: "public",
        capabilities: [],
      }),
    }),
  );
  await page.goto("/workspace/evaluations");
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await expect(
    page.getByRole("heading", { name: "无 Agent 评测查看权限" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Agent 评测", exact: true }),
  ).not.toBeVisible();
  await expect(page.getByRole("table")).not.toBeVisible();
});

test("switching batches ignores an older in-flight detail response", async ({
  page,
}) => {
  const old = evaluationFixture("batch-old");
  const current = evaluationFixture("batch-new");
  current.results[0]!.case.title = "新批次的独立用例";
  await mockEvaluations(page, [old, current]);
  let releaseOld!: () => void;
  const released = new Promise<void>((resolve) => {
    releaseOld = resolve;
  });
  let notifyRequested!: () => void;
  const requested = new Promise<void>((resolve) => {
    notifyRequested = resolve;
  });
  await page.route(
    "**/api/operations/evaluations/executions/batch-old",
    async (route) => {
      notifyRequested();
      await released;
      // TanStack Query aborts the abandoned fetch; that response may no longer
      // have a receiver, but must never replace the currently selected batch.
      await route
        .fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(old),
        })
        .catch(() => undefined);
    },
  );
  await page.goto("/workspace/evaluations");
  await requested;
  await page.getByLabel("评测批次").selectOption("batch-new");
  await expect(
    page.getByRole("table").getByText("新批次的独立用例", { exact: true }),
  ).toBeVisible();
  releaseOld();
  await expect(page.getByLabel("评测批次")).toHaveValue("batch-new");
  await expect(
    page.getByRole("table").getByText("新批次的独立用例", { exact: true }),
  ).toBeVisible();
});
