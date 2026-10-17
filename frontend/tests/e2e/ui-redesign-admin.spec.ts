import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { mockAdmin } from "../fixtures/ui-admin";
import { mockAdminGraph } from "../fixtures/ui-admin-graph";

import { refreshMockUser } from "./utils/refresh-mock-user";

const directory = process.env.UI_ADMIN_DIR;
async function capture(page: Page, name: string) {
  if (!directory) return;
  await mkdir(directory, { recursive: true });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>((done) =>
      requestAnimationFrame(() => requestAnimationFrame(() => done())),
    );
  });
  await page.screenshot({
    path: resolve(directory, name + ".png"),
    animations: "disabled",
  });
  await writeFile(
    resolve(directory, name + ".json"),
    JSON.stringify(
      await page.evaluate(() => ({
        url: location.href,
        viewport: { width: innerWidth, height: innerHeight },
        documentWidth: document.documentElement.scrollWidth,
        theme: document.documentElement.className,
        data: "Mock APIs; image and documents explicitly software fixtures; no live Gateway writes",
      })),
      null,
      2,
    ),
  );
}
const routes = [
  ["library", "文献库", "木渎方志校勘样本（软件测试）"],
  ["knowledge-graph", "知识图谱", "康熙帝"],
  ["quality", "质量中心", "请核对这条方志引文的卷次与出处。"],
  ["evaluations", "星羲 Agent 自动评测", "70.0%"],
  ["operations", "运营中心", "87.5%"],
  ["scheduled-tasks", "Scheduled tasks", "每日方志线索研读"],
] as const;
for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 360, height: 800 },
])
  for (const theme of ["light", "dark"]) {
    test(`administrative workspaces ${viewport.width} ${theme}`, async ({
      page,
    }) => {
      test.setTimeout(90000);
      await page.setViewportSize(viewport);
      await page.addInitScript(
        (value) => localStorage.setItem("theme", value),
        theme,
      );
      await mockAdmin(page);
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      for (const [route, title, loaded] of routes) {
        await page.goto("/workspace/" + route);
        if (route === "scheduled-tasks")
          await expect(
            page.getByTestId("scheduled-task-create-form"),
          ).toBeVisible();
        else
          await expect(
            page.getByRole("heading", { name: title, exact: true }),
          ).toBeVisible();
        await expect(
          page.getByText(loaded, { exact: false }).first(),
        ).toBeVisible({ timeout: 15000 });
        await capture(page, `${route}-${viewport.width}-${theme}`);
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
        ).toBe(viewport.width);
      }
      expect(errors).toEqual([]);
    });
  }

test("library facsimile, review decisions and exact release publication remain traceable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const state = await mockAdmin(page);
  await page.goto("/workspace/library");
  await page.getByRole("button", { name: "复核", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "文本人工复核" });
  await expect(dialog.getByText("OCR 未采集")).toBeVisible();
  await expect(dialog.getByText("OCR 0%")).toHaveCount(0);
  await page.getByRole("button", { name: "原件影印", exact: true }).click();
  const image = dialog.getByAltText("已上传的原始影像");
  await expect(image).toBeVisible();
  await expect
    .poll(() =>
      image.evaluate((node) => (node as HTMLImageElement).naturalWidth),
    )
    .toBeGreaterThan(0);
  await capture(page, "library-facsimile-1440-light");
  await page.getByRole("button", { name: "标记争议", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("必须填写复核意见");
  expect(state.decisions).toHaveLength(0);
  await dialog
    .getByPlaceholder("退回或争议时必填")
    .fill("核对原件后记录异文。");
  await page.getByRole("button", { name: "标记争议", exact: true }).click();
  await expect.poll(() => state.decisions.length).toBe(1);
  expect(state.decisions[0]).toEqual({
    items: [
      {
        target_type: "page",
        target_id: "clean-page-1",
        decision: "disputed",
        comment: "核对原件后记录异文。",
      },
    ],
  });
  await expect(dialog.getByText("有争议", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "通过", exact: true }).click();
  await expect(dialog.getByText("已通过", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "按片段复核", exact: true }).click();
  await dialog.getByRole("button", { name: "通过", exact: true }).click();
  await expect.poll(() => state.chunkStatus).toBe("reviewed");
  await dialog.getByRole("button", { name: "原始文本", exact: true }).click();
  await dialog
    .getByRole("heading", { name: "清洗文本" })
    .scrollIntoViewIfNeeded();
  await capture(page, "library-slices-1440-light");
  await page.keyboard.press("Escape");
  await page.getByRole("checkbox", { name: "选择 校勘样本.png" }).check();
  await page.getByRole("button", { name: "知识版本 (1)", exact: true }).click();
  const release = page.getByRole("dialog", { name: "知识版本", exact: true });
  await release
    .getByPlaceholder("填写本次发布说明")
    .fill("软件验证：发布已核对文献");
  await capture(page, "library-releases-1440-light");
  await release
    .getByRole("button", { name: "发布并启用", exact: true })
    .click();
  await expect.poll(() => state.publishes.length).toBe(1);
  expect(state.publishes[0]).toMatchObject({
    chunk_set_ids: ["chunkset-1"],
    expected_state_version: 1,
  });
});

test("quality failures retain written notes and mobile sheet returns focus", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await mockAdmin(page);
  state.qualityFailure = true;
  await page.goto("/workspace/quality");
  const trigger = page.getByRole("button", { name: "处理", exact: true });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "反馈核对与处理" });
  await expect(dialog).toBeVisible();
  await dialog
    .getByPlaceholder("记录核对结果或后续处理要求")
    .fill("需要核对卷次，暂保留本次意见。");
  await dialog
    .getByRole("button", { name: "保存处理结果", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(
    dialog.getByPlaceholder("记录核对结果或后续处理要求"),
  ).toHaveValue("需要核对卷次，暂保留本次意见。");
  await capture(page, "quality-review-390-light");
  state.qualityFailure = false;
  await dialog
    .getByRole("button", { name: "保存处理结果", exact: true })
    .click();
  await expect.poll(() => state.reviews.length).toBe(2);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("read-only quality users retain capability boundaries", async ({
  page,
}) => {
  await mockAdmin(page);
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "quality-reader",
        email: "reader@test.local",
        system_role: "user",
        business_role: "government",
        capabilities: ["quality:read", "governance:read"],
        needs_setup: false,
      },
    }),
  );
  await page.goto("/workspace/quality");
  await refreshMockUser(page);
  await expect(
    page.getByRole("button", { name: "处理", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "查看", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "保存处理结果", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByPlaceholder("记录核对结果或后续处理要求")).toHaveCount(
    0,
  );
});

test("source review conflicts preserve notes and remain retryable", async ({
  page,
}) => {
  const state = await mockAdmin(page);
  state.reviewFailure = true;
  await page.goto("/workspace/library");
  await page.getByRole("button", { name: "复核", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "文本人工复核" });
  const notes = dialog.getByPlaceholder("退回或争议时必填");
  await notes.fill("保留已核对的异文记录");
  await dialog.getByRole("button", { name: "标记争议", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("版本已改变");
  await expect(notes).toHaveValue("保留已核对的异文记录");
  expect(state.sourceStatus).toBe("pending");
  state.reviewFailure = false;
  await dialog.getByRole("button", { name: "标记争议", exact: true }).click();
  await expect(dialog.getByText("有争议", { exact: true })).toBeVisible();
  expect(state.decisions).toHaveLength(2);
});

test("release pointer conflicts preserve publication notes and expected version", async ({
  page,
}) => {
  const state = await mockAdmin(page);
  state.sourceStatus = state.chunkStatus = "reviewed";
  state.publishFailure = true;
  await page.goto("/workspace/library");
  await page.getByRole("checkbox", { name: "选择 校勘样本.png" }).check();
  await page.getByRole("button", { name: "知识版本 (1)", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "知识版本", exact: true });
  const notes = dialog.getByPlaceholder("填写本次发布说明");
  await notes.fill("冲突时保留本次发布说明");
  await dialog.getByRole("button", { name: "发布并启用", exact: true }).click();
  await expect(dialog.getByText("测试：生效版本已更新")).toBeVisible();
  await expect(notes).toHaveValue("冲突时保留本次发布说明");
  expect(state.releaseVersion).toBe(1);
  expect(state.publishes[0]).toMatchObject({
    expected_state_version: 1,
    chunk_set_ids: ["chunkset-1"],
  });
  state.publishFailure = false;
  await dialog.getByRole("button", { name: "发布并启用", exact: true }).click();
  await expect.poll(() => state.releaseVersion).toBe(2);
});

test("graph review workspace persists its explicit mode and shows evidence-bound controls", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockAdmin(page);
  const graph = await mockAdminGraph(page, true);
  await page.route("**/api/knowledge-graph/query*", (route) =>
    route.fulfill({
      json: {
        query: "gukuang",
        status: "supported",
        message: "软件测试",
        candidates: graph.nodes.filter((node) => node.id === "gukuang"),
        nodes: graph.nodes.filter((node) =>
          ["gukuang", "mudu"].includes(node.id),
        ),
        edges: graph.edges.filter((edge) => edge.id === "gm"),
        evidence: [],
        truncated: false,
        max_depth: 2,
        max_nodes: 200,
        release_id: "release",
      },
    }),
  );
  await page.goto("/workspace/knowledge-graph");
  await page
    .getByRole("button", { name: "打开审核与录入工作台", exact: true })
    .click();
  await expect(page).toHaveURL(/manage=1/);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "返回全局浏览", exact: true }),
  ).toBeVisible();
  await page.goto(
    "/workspace/knowledge-graph?manage=1&view=graph&entity=gukuang",
  );
  const inspector = page.getByRole("complementary", {
    name: "主体关系与史料考据",
  });
  await expect(inspector).toBeVisible();
  const card = inspector.locator("#graph-relation-gm");
  await card.getByRole("button", { name: "修改审核结果" }).click();
  await card.getByRole("button", { name: "有争议", exact: true }).click();
  await expect(
    card.getByRole("button", { name: "保存审核结果" }),
  ).toBeDisabled();
  await card.getByLabel(/审核备注/).fill("需对照卷页核对年代与地名");
  await expect(
    card.getByRole("button", { name: "保存审核结果" }),
  ).toBeEnabled();
  await capture(page, "knowledge-graph-review-1440-light");
});
