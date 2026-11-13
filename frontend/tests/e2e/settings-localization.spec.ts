import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const origin = new URL(
  process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
).origin;

test("skills can reload after the Gateway becomes available", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  let available = false;
  await page.route("**/api/skills", (route) =>
    available
      ? route.fulfill({
          json: {
            skills: [
              {
                name: "deep-research",
                description: "Research",
                category: "public",
                enabled: true,
                editable: false,
              },
            ],
          },
        })
      : route.fulfill({ status: 404, json: { detail: "Not Found" } }),
  );
  await page.goto("/workspace/chats/new");
  await page
    .locator("[data-sidebar='sidebar']")
    .getByRole("button", { name: "设置", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "设置", exact: true });
  await dialog.getByRole("button", { name: "研究能力", exact: true }).click();
  await expect(dialog.getByRole("alert")).toContainText("暂时无法读取研究能力");
  available = true;
  await dialog.getByRole("button", { name: "重新加载", exact: true }).click();
  await expect(
    dialog.getByRole("switch", { name: "深度资料研究", exact: true }),
  ).toBeChecked();
  await expect(dialog.getByRole("alert")).toHaveCount(0);
});

test("legacy English preferences open all settings modules in Chinese with Xingxi content", async ({
  page,
}) => {
  await page
    .context()
    .addCookies([{ name: "locale", value: "en-US", url: origin }]);
  mockLangGraphAPI(page, {
    skills: [
      {
        name: "skill-reviewer",
        description: "Reviews DeerFlow skills",
        category: "public",
        enabled: true,
      },
      {
        name: "claude-to-deerflow",
        description: "Interact with DeerFlow",
        category: "public",
        enabled: true,
      },
    ],
  });
  await page.route("**/api/v1/auth/users", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/memory", (route) =>
    route.fulfill({ status: 503, json: { detail: "Failed to load memory" } }),
  );
  let enabledSkill: string | null = null;
  await page.route("**/api/skills/skill-reviewer", (route) => {
    enabledSkill = new URL(route.request().url()).pathname;
    return route.fulfill({ json: { success: true } });
  });
  let toolUpdate: unknown;
  await page.route("**/api/mcp/config", (route) => {
    if (route.request().method() === "PUT")
      toolUpdate = route.request().postDataJSON();
    return route.fulfill({
      json: {
        mcp_servers: {
          github: {
            enabled: true,
            description: "GitHub MCP server for repository operations",
          },
        },
      },
    });
  });
  const externalRequests: string[] = [];
  page.on("request", (request) => {
    if (
      /star-history|deerflow\.tech|github\.com\/bytedance/.test(request.url())
    )
      externalRequests.push(request.url());
  });

  await page.goto("/workspace/chats/new");
  await page
    .locator("[data-sidebar='sidebar']")
    .getByRole("button", { name: "设置", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "设置", exact: true });
  for (const [section, heading] of [
    ["账号", "个人信息"],
    ["外观", "主题"],
    ["通知", "通知"],
    ["消息渠道", "消息渠道"],
    ["记忆", "记忆"],
    ["辅助功能", "辅助功能"],
    ["研究能力", "研究能力"],
    ["关于", "关于星羲弦沚"],
  ]) {
    await dialog.getByRole("button", { name: section, exact: true }).click();
    await expect(
      dialog.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    await expect(dialog).not.toContainText(
      /DeerFlow|About DeerFlow|Agent Skills|Settings|MCP|PostgreSQL|usage_metadata|原始 JSON|当前版本|skill-reviewer/,
    );
  }
  await expect(dialog).toContainText("吴文化与木渎地域文史");
  expect(externalRequests).toEqual([]);
  await dialog.getByRole("button", { name: "研究能力", exact: true }).click();
  await expect(dialog.getByText("研究流程检查", { exact: true })).toBeVisible();
  await dialog.getByRole("switch", { name: "研究流程检查" }).click();
  await expect.poll(() => enabledSkill).toBe("/api/skills/skill-reviewer");
  await dialog.getByRole("button", { name: "辅助功能", exact: true }).click();
  await dialog.getByRole("switch", { name: "项目资料查找" }).click();
  await expect
    .poll(() => toolUpdate)
    .toMatchObject({ mcp_servers: { github: { enabled: false } } });
  await dialog.getByRole("button", { name: "记忆", exact: true }).click();
  await expect(dialog.getByRole("alert")).toHaveText(
    "暂时无法读取记忆，请稍后重试。",
  );
});

test("an explicit language choice persists when a settings section mounts and the page reloads", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  await page.goto("/workspace/chats/new");
  const sidebar = page.locator("[data-sidebar='sidebar']");
  await sidebar.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("dialog").getByRole("combobox").click();
  await page.getByRole("option", { name: "English", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Settings", exact: true });
  await expect(dialog).toBeVisible();
  await dialog
    .getByRole("button", { name: "Notification", exact: true })
    .click();
  await expect(dialog).toContainText("Xingxi");
  await page.reload();
  await sidebar.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "Settings", exact: true }),
  ).toBeVisible();
  expect(
    (await page.context().cookies()).find(
      (cookie) => cookie.name === "xingxi_locale",
    )?.value,
  ).toBe("en-US");
});

test("memory editing uses readable certainty choices and preserves the saved category", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  const section = { summary: "", updatedAt: "2026-10-29T00:00:00Z" };
  const memory = {
    version: "internal-schema-v1",
    lastUpdated: "2026-10-29T00:00:00Z",
    effectiveEnabled: true,
    user: {
      workContext: section,
      personalContext: section,
      topOfMind: section,
    },
    history: {
      recentMonths: section,
      earlierContext: section,
      longTermBackground: section,
    },
    facts: [] as Array<Record<string, unknown>>,
  };
  await page.route("**/api/memory", (route) => route.fulfill({ json: memory }));
  let saved: Record<string, unknown> | undefined;
  await page.route("**/api/memory/facts", (route) => {
    saved = route.request().postDataJSON() as Record<string, unknown>;
    memory.facts = [
      {
        ...saved,
        id: "private-fact-id",
        source: "manual",
        createdAt: memory.lastUpdated,
      },
    ];
    return route.fulfill({ json: memory });
  });
  await page.goto("/workspace/chats/new");
  await page
    .locator("[data-sidebar='sidebar']")
    .getByRole("button", { name: "设置", exact: true })
    .click();
  const settings = page.getByRole("dialog", { name: "设置", exact: true });
  await settings.getByRole("button", { name: "记忆", exact: true }).click();
  await settings.getByRole("button", { name: "添加事实", exact: true }).click();
  const editor = page.getByRole("dialog", {
    name: "添加记忆事实",
    exact: true,
  });
  await expect(editor.getByLabel("类别", { exact: true })).toHaveValue(
    "背景信息",
  );
  await expect(editor.getByRole("spinbutton")).toHaveCount(0);
  await editor.getByLabel("内容", { exact: true }).fill("关注木渎地方志");
  await editor
    .getByLabel("把握程度", { exact: true })
    .selectOption({ label: "极高" });
  await editor.getByRole("button", { name: "保存事实", exact: true }).click();
  await expect
    .poll(() => saved)
    .toEqual({
      content: "关注木渎地方志",
      category: "context",
      confidence: 0.95,
    });
  await expect(editor).not.toBeVisible();
  await expect(settings).toContainText("关注木渎地方志");
  await expect(settings).not.toContainText(
    /internal-schema-v1|private-fact-id|context|0\.95/,
  );
});
