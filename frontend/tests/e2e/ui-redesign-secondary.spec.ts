import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import {
  mockLogin,
  mockSecondary,
  secondaryProject,
} from "../fixtures/ui-secondary";

import { refreshMockUser } from "./utils/refresh-mock-user";

const output = process.env.UI_SECONDARY_DIR;
const loginOrigin = "http://127.0.0.1:3107";
async function capture(page: Page, name: string) {
  if (!output) return;
  await mkdir(output, { recursive: true });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>((done) =>
      requestAnimationFrame(() => requestAnimationFrame(() => done())),
    );
  });
  await page.screenshot({
    path: resolve(output, name + ".png"),
    animations: "disabled",
  });
}

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 360, height: 800 },
])
  for (const theme of ["light", "dark"]) {
    test(`auxiliary surfaces ${viewport.width} ${theme}`, async ({ page }) => {
      test.setTimeout(60000);
      await page.setViewportSize(viewport);
      await page.addInitScript(
        (value) => localStorage.setItem("theme", value),
        theme,
      );
      await mockSecondary(page);
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      for (const [route, title] of [
        ["glossary", "古文释读展签"],
        ["name-authority", "古籍异名辨析"],
        ["projects", "研究项目"],
      ]) {
        await page.goto("/workspace/" + route);
        await expect(
          page.getByRole("heading", { name: title, exact: true }),
        ).toBeVisible();
        if (route === "projects")
          await expect(
            page.getByRole("link", {
              name: secondaryProject.name,
              exact: true,
            }),
          ).toBeVisible();
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
        ).toBe(viewport.width);
        await capture(page, `${route}-${viewport.width}-${theme}`);
      }
      await page.goto("/workspace/projects/" + secondaryProject.id);
      await expect(page.getByText("项目还没有文献")).toBeVisible();
      await capture(page, `project-detail-${viewport.width}-${theme}`);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(viewport.width);
      await mockLogin(page);
      await page.goto(loginOrigin + "/login");
      await expect(page.locator("#email")).toBeVisible();
      await expect(page.locator("#password")).toBeVisible();
      await capture(page, `login-${viewport.width}-${theme}`);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(viewport.width);
      expect(errors).toEqual([]);
    });
  }

test("glossary preserves original, source and uncertainty through failure, copy and print", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => {
    const state = window as typeof window & {
      copiedLabel?: string;
      printedLabel?: boolean;
    };
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (text: string) => {
          state.copiedLabel = text;
        },
      },
    });
    window.print = () => {
      state.printedLabel = true;
    };
  });
  const state = await mockSecondary(page);
  state.glossFailure = true;
  await page.goto("/workspace/glossary");
  const original = "某水未详，沿河而居。（软件测试）";
  await page
    .getByLabel("展签标题", { exact: true })
    .fill("水系释读（软件测试）");
  await page.getByLabel(/^古文原文/).fill(original);
  await page.getByRole("button", { name: "生成释读展签", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "释读服务暂不可用",
  );
  await expect(page.getByLabel(/^古文原文/)).toHaveValue(original);
  state.glossFailure = false;
  await page.getByRole("button", { name: "生成释读展签", exact: true }).click();
  await expect(
    page.getByText("辅助释读，需核对原文", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("待考：水名所指")).toBeVisible();
  await expect(
    page.locator("article").getByText(original, { exact: true }),
  ).toBeVisible();
  expect(state.glossRequests[1]?.text).toBe(original);
  await capture(page, "glossary-result-1440-light");
  await page.getByRole("button", { name: "复制展签", exact: true }).click();
  const copied = await page.evaluate(
    () => (window as typeof window & { copiedLabel?: string }).copiedLabel,
  );
  expect(copied).toContain(original);
  expect(copied).toContain("出处：");
  expect(copied).toContain("辅助释读，需核对原文");
  await page.getByRole("button", { name: "打印", exact: true }).click();
  expect(
    await page.evaluate(
      () => (window as typeof window & { printedLabel?: boolean }).printedLabel,
    ),
  ).toBe(true);
});

test("name authority retains ambiguity, all variants and exact evidence after retry", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const state = await mockSecondary(page);
  state.nameFailure = true;
  await page.goto("/workspace/name-authority");
  await expect(
    page.getByRole("button", { name: "依据资料出处辨析" }),
  ).toBeDisabled();
  await page.getByLabel("候选 1 名称", { exact: true }).fill("胥江");
  await page.getByLabel("候选 2 名称", { exact: true }).fill("胥溪");
  await page
    .getByLabel("候选 1 资料出处编号", { exact: true })
    .fill("ev-1, ev-1，ev-2");
  await page.getByLabel("候选 2 资料出处编号", { exact: true }).fill("ev-3");
  await page.getByRole("button", { name: "依据资料出处辨析" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "异名服务暂不可用",
  );
  await expect(page.getByLabel("候选 1 名称", { exact: true })).toHaveValue(
    "胥江",
  );
  state.nameFailure = false;
  await page.getByRole("button", { name: "依据资料出处辨析" }).click();
  await expect(
    page.getByRole("heading", { name: "暂不自动确定首选名" }),
  ).toBeVisible();
  await expect(page.getByText("需要人工复核", { exact: true })).toBeVisible();
  await expect(page.getByText(/全部保留：胥江、胥溪/)).toBeVisible();
  expect(state.nameRequests[1]).toMatchObject({
    variants: [
      { name: "胥江", evidence_ids: ["ev-1", "ev-2"] },
      { name: "胥溪", evidence_ids: ["ev-3"] },
    ],
  });
  await capture(page, "name-authority-result-1440-light");
});

test("project creation protects composition and errors can retry", async ({
  page,
}) => {
  const state = await mockSecondary(page);
  state.projectFailure = true;
  await page.goto("/workspace/projects");
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "项目暂不可用",
  );
  state.projectFailure = false;
  await page.getByRole("button", { name: "重新加载", exact: true }).click();
  await expect(
    page.getByRole("link", { name: secondaryProject.name, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "新建项目", exact: true }).click();
  const name = page.getByLabel("项目名称", { exact: true });
  await name.fill("水路沿革新课题");
  await name.dispatchEvent("keydown", {
    key: "Enter",
    code: "Enter",
    isComposing: true,
  });
  expect(state.projects).toHaveLength(1);
  await page.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  expect(state.projects).toHaveLength(2);
  await expect(
    page.getByRole("link", { name: "水路沿革新课题", exact: true }),
  ).toBeVisible();
});

test("public reader cannot create or manage research projects", async ({
  page,
}) => {
  await mockSecondary(page);
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "reader",
        email: "reader@test.local",
        system_role: "user",
        business_role: "public",
        capabilities: [],
        needs_setup: false,
      },
    }),
  );
  await page.goto("/workspace/projects");
  await refreshMockUser(page);
  await expect(
    page.getByText("当前角色不使用研究项目", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "新建项目", exact: true }),
  ).toHaveCount(0);
});

test("login failure retains input and rejects an external return path", async ({
  page,
}) => {
  await mockLogin(page);
  await page.goto(
    loginOrigin +
      "/login?next=" +
      encodeURIComponent("//example.invalid/escape"),
  );
  await page.locator("#email").fill("software-test@example.invalid");
  await page.locator("#password").fill("software-test-password");
  await page.locator('form button[type="submit"]').click();
  await expect(
    page.getByText("测试：邮箱或密码不正确", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("#email")).toHaveValue(
    "software-test@example.invalid",
  );
  await page.route("**/api/v1/auth/oauth/software-sso?**", (route) =>
    route.fulfill({ contentType: "text/html", body: "软件测试 SSO 跳转" }),
  );
  await page.getByRole("button", { name: /测试机构 SSO/ }).click();
  await expect(page).toHaveURL(/next=%2Fworkspace$/);
});

test("initial setup exposes the administrator entry without ordinary signup", async ({
  page,
}) => {
  await mockLogin(page, true);
  await page.goto(loginOrigin + "/login");
  await expect(page.locator('a[href="/setup"]')).toBeVisible();
  await expect(page.getByRole("button", { name: /Sign up|注册/ })).toHaveCount(
    0,
  );
});
