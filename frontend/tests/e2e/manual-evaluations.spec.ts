import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test("simple manual evaluation explains saved results and blocks empty answers", async ({
  page,
}, testInfo) => {
  mockLangGraphAPI(page);
  const active = {
    id: "demo",
    name: "演示：无证据拒答",
    question: "请介绍灵岩山。",
    active: true,
    expected_status: "refused",
    min_citations: 0,
    required_terms: [],
    created_by: "admin",
    created_at: "2026-10-01T00:00:00Z",
  };
  const answer = "当前检索范围内暂无明确记载。可用证据 0 条。";
  let runs = [
    {
      id: "saved",
      release_id: "release-test",
      status: "completed",
      total: 1,
      passed: 1,
      pass_rate: 1,
      created_by: "local-demo",
      created_at: active.created_at,
      results: [
        {
          case_id: active.id,
          actual_status: "refused",
          citation_count: 0,
          answer,
          passed: true,
          failure_reasons: [] as string[],
        },
      ],
    },
  ];
  let posted: Record<string, unknown> | undefined;
  await page.route("**/api/operations/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const reply = (data: unknown) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(data),
      });
    if (path.endsWith("/cases"))
      return reply([
        active,
        { ...active, id: "old", name: "旧用例", active: false },
      ]);
    if (path.endsWith("/runs") && route.request().method() === "POST") {
      posted = route.request().postDataJSON();
      const observations = posted!.observations as Array<{
        case_id: string;
        answer: string;
        actual_status: string;
        citation_count: number;
      }>;
      const result = {
        ...observations[0]!,
        passed: false,
        failure_reasons: ["expected status refused, got answered"],
      };
      const next = {
        ...runs[0]!,
        id: "failed",
        passed: 0,
        pass_rate: 0,
        created_by: "admin",
        results: [result],
      };
      runs = [next, ...runs];
      return reply(next);
    }
    if (path.endsWith("/runs")) return reply(runs);
    if (path.endsWith("/dashboard"))
      return reply({ hot_entities: [], answer_count: 0 });
    return reply([]);
  });
  await page.goto("/workspace/operations");
  await page.getByRole("button", { name: "回归评测", exact: true }).click();
  const panel = page.getByRole("region", { name: "人工观测评测", exact: true });
  await expect(panel.getByText("1 / 1 条规则通过")).toBeVisible();
  await expect(panel.getByText(answer, { exact: true })).toBeVisible();
  await panel.getByText("录入下一次回答", { exact: true }).click();
  await expect(panel.getByRole("heading", { name: "旧用例" })).toHaveCount(0);
  const submit = panel.getByRole("button", { name: "保存并查看结果" });
  await expect(submit).toBeDisabled();
  await panel.getByRole("button", { name: "使用上次回答" }).click();
  await expect(submit).toBeEnabled();
  await panel.getByLabel("本次回答状态").selectOption("answered");
  await submit.click();
  await expect(panel.getByText("0 / 1 条规则通过")).toBeVisible();
  await expect(
    panel.getByText("期望拒答，本次标记为回答", { exact: true }),
  ).toBeVisible();
  expect((posted!.observations as unknown[]).length).toBe(1);
  await page.reload();
  await page.getByRole("button", { name: "回归评测", exact: true }).click();
  await expect(panel.getByText("0 / 1 条规则通过")).toBeVisible();
  await panel.getByText("查看历史记录（2 次）", { exact: true }).click();
  await expect(panel.getByText("1 / 1 通过", { exact: false })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("simple-manual-evaluation.png"),
    fullPage: true,
  });
});
