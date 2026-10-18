import { expect, test, type Page } from "@playwright/test";

import type {
  AgentCaseInput,
  ManagedAgentCase,
} from "../../src/core/operations/evaluations";
import {
  evaluationCases,
  evaluationFixture,
} from "../fixtures/agent-evaluations";

import { mockLangGraphAPI } from "./utils/mock-api";

async function mockQuestionManagement(page: Page) {
  mockLangGraphAPI(page);
  const cases: ManagedAgentCase[] = evaluationCases.map((item) => ({
    ...item,
    active: true,
    builtin: true,
  }));
  const methods = evaluationCases
    .filter((item) => item.mode === "pro")
    .map((item) => ({
      ...item,
      description: `固定回放方法：${item.title}`,
      required_tool: "search_sources",
      expected_terms: ["测试溪"],
    }));
  const state = { failCreate: false, executed: [] as string[] };
  await page.route("**/api/operations/evaluations/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let body: unknown = {};
    let status = 200;
    if (path.endsWith("/catalog"))
      body = {
        available: true,
        version: "test",
        execution_mode: "replay",
        core_count: 6,
        cases: cases.filter((item) => item.active),
      };
    else if (path.endsWith("/cases")) {
      if (request.method() === "GET")
        body = { execution_mode: "replay", methods, cases };
      else if (state.failCreate) {
        status = 503;
        body = { detail: "保存暂时失败" };
      } else {
        const input = request.postDataJSON() as AgentCaseInput;
        const created = {
          ...evaluationCases.find(
            (item) =>
              item.scenario === input.scenario && item.mode === input.mode,
          )!,
          ...input,
          id: "custom-question",
          active: true,
          builtin: false,
        };
        cases.push(created);
        body = created;
        status = 201;
      }
    } else if (path.includes("/cases/")) {
      const item = cases.find((entry) => path.includes(entry.id))!;
      item.active = request.method() !== "DELETE";
      body = item;
    } else if (path.endsWith("/executions") && request.method() === "POST") {
      state.executed = (
        request.postDataJSON() as { case_ids: string[] }
      ).case_ids;
      body = evaluationFixture("single-question-batch");
      status = 202;
    } else if (path.endsWith("/executions")) body = [];
    else body = evaluationFixture("single-question-batch");
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
  return state;
}

test("admins inspect methods, add/delete/restore and run an individual question", async ({
  page,
}) => {
  const state = await mockQuestionManagement(page);
  await page.goto("/workspace/evaluations");
  await page
    .getByRole("button", { name: "测试问题与方法", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText(/新增问题沿用所选方法/)).toBeVisible();
  const first = dialog.getByRole("article").first();
  await first.getByText("查看测试方法与判定规则").click();
  await expect(first.getByText(/固定回放方法/)).toBeVisible();
  await expect(first.getByText(/预期工具/)).toBeVisible();
  await dialog.getByRole("button", { name: "新增问题", exact: true }).click();
  await dialog.getByLabel("题目名称", { exact: true }).fill("自定义桥梁位置");
  await dialog
    .getByLabel("测试问题", { exact: true })
    .fill("测试桥位于哪条溪流？");
  state.failCreate = true;
  await dialog.getByRole("button", { name: "保存问题", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("保存暂时失败");
  await expect(dialog.getByLabel("测试问题", { exact: true })).toHaveValue(
    "测试桥位于哪条溪流？",
  );
  state.failCreate = false;
  await dialog.getByRole("button", { name: "保存问题", exact: true }).click();
  const custom = dialog.getByRole("article", {
    name: "测试问题：自定义桥梁位置 · pro",
  });
  await expect(custom.getByText("测试桥位于哪条溪流？")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "运行全部 31 项" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "测试问题与方法", exact: true })
    .click();
  await custom.getByRole("button", { name: /删除题目/ }).click();
  await expect(custom).not.toBeVisible();
  await dialog.getByLabel("显示已删除问题").check();
  await expect(custom.getByText(/已删除/)).toBeVisible();
  await custom.getByRole("button", { name: /恢复题目/ }).click();
  await expect(custom.getByText(/启用中/)).toBeVisible();
  await custom.getByRole("button", { name: /运行题目/ }).click();
  await expect(dialog).not.toBeVisible();
  await expect.poll(() => state.executed).toEqual(["custom-question"]);
});

test("governance readers see full questions and methods without mutation controls", async ({
  page,
}) => {
  await mockQuestionManagement(page);
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "reader",
        system_role: "user",
        business_role: "government",
        capabilities: ["governance:read"],
      }),
    }),
  );
  await page.goto("/workspace/evaluations");
  await page
    .getByRole("button", { name: "测试问题与方法", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("article")).toHaveCount(30);
  await expect(
    dialog.getByRole("button", { name: "新增问题", exact: true }),
  ).not.toBeVisible();
  await expect(
    dialog.getByRole("button", { name: /删除题目|运行题目|恢复题目/ }),
  ).not.toBeVisible();
  await dialog.getByLabel("搜索测试问题").fill("古文释义");
  await expect(dialog.getByRole("article")).toHaveCount(3);
});
