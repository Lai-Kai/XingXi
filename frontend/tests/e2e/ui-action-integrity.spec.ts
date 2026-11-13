import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI, MOCK_THREAD_ID } from "./utils/mock-api";
import { refreshMockUser } from "./utils/refresh-mock-user";

const navigation = [
  ["文史检索", "/workspace"],
  ["文献库", "/workspace/library"],
  ["星羲智能体", "/workspace/agent"],
  ["研究项目", "/workspace/projects"],
  ["古舆地图", "/workspace/map"],
  ["古文展签", "/workspace/glossary"],
  ["知识图谱", "/workspace/knowledge-graph"],
  ["异名辨析", "/workspace/name-authority"],
  ["质量中心", "/workspace/quality"],
  ["Agent 评测", "/workspace/evaluations"],
  ["运营中心", "/workspace/operations"],
  ["最近研究", "/workspace/chats"],
] as const;

async function isolateBusinessReads(page: Page) {
  // An explicit unavailable response keeps this navigation check independent
  // from product data. Feature tests exercise the successful API payloads.
  await page.route("**/api/**", (route) =>
    route.fulfill({ status: 503, json: { detail: "导航测试：服务暂不可用" } }),
  );
  mockLangGraphAPI(page);
  await page.route("**/api/research-feed/daily?**", (route) =>
    route.fulfill({
      json: {
        kind: "daily_grounded",
        generated_for: "2026-10-20",
        next_refresh_at: "2099-10-21T00:00:00+08:00",
        items: [],
      },
    }),
  );
}

for (const width of [1440, 390]) {
  test(`all public navigation entries reach their pages at ${width}px`, async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width, height: 900 });
    await isolateBusinessReads(page);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const failedDocuments: string[] = [];
    page.on("response", (response) => {
      if (response.request().isNavigationRequest() && response.status() >= 400)
        failedDocuments.push(`${response.status()} ${response.url()}`);
    });
    await page.goto("/workspace/chats/new");

    for (const [label, href] of navigation) {
      await test.step(label, async () => {
        if (width < 768)
          await page.locator("[data-sidebar='trigger']").first().click();
        const sidebar = page.locator("[data-sidebar='sidebar']");
        await sidebar.getByRole("link", { name: label, exact: true }).click();
        await expect(page).toHaveURL(new RegExp(`${href}$`));
        if (width < 768)
          await expect(page.locator("[data-mobile='true']")).toHaveCount(0);
        await expect(page.locator("main").first()).toBeVisible();
        await expect(
          page.getByText("This page could not be found."),
        ).toHaveCount(0);
      });
    }
    expect(failedDocuments).toEqual([]);
    expect(errors).toEqual([]);
  });
}

test("agent-tagged history entries open the actual conversation", async ({
  page,
}) => {
  mockLangGraphAPI(page, {
    threads: [
      {
        thread_id: MOCK_THREAD_ID,
        title: "带智能体元数据的历史研究",
        agent_name: "xingxi",
        metadata: { agent_name: "xingxi" },
        messages: [
          { type: "ai", id: "history-answer", content: "原会话的历史回答" },
        ],
      },
    ],
  });
  await page.goto("/workspace/chats");
  const link = page.locator(".xingxi-module").getByRole("link", {
    name: /带智能体元数据的历史研究/,
  });
  await expect(link).toHaveAttribute(
    "href",
    `/workspace/chats/${MOCK_THREAD_ID}`,
  );
  await link.click();
  await expect(page).toHaveURL(
    new RegExp(`/workspace/chats/${MOCK_THREAD_ID}$`),
  );
  await expect(page.getByTestId("main-message-list")).toContainText(
    "原会话的历史回答",
  );
});

test("sharing from a local deployment keeps its origin and conversation", async ({
  page,
}) => {
  mockLangGraphAPI(page, {
    threads: [
      {
        thread_id: MOCK_THREAD_ID,
        title: "分享测试研究",
        agent_name: "xingxi",
        metadata: { agent_name: "xingxi" },
      },
    ],
  });
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value: string) => {
          document.documentElement.dataset.copiedLink = value;
        },
      },
    });
  });
  await page.goto("/workspace/chats/new");
  const item = page.locator("[data-sidebar='menu-item']").filter({
    has: page.getByRole("link", { name: "分享测试研究", exact: true }),
  });
  await item.hover();
  await item.getByRole("button", { name: "更多", exact: true }).click();
  await page.getByRole("menuitem", { name: "分享", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute(
    "data-copied-link",
    `${new URL(page.url()).origin}/workspace/chats/${MOCK_THREAD_ID}`,
  );
});

for (const [path, message] of [
  ["quality", "无质量治理权限"],
  ["operations", "无运营治理权限"],
] as const) {
  test(`mobile users can leave the ${path} permission screen`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await isolateBusinessReads(page);
    await page.route("**/api/v1/auth/me", (route) =>
      route.fulfill({
        json: {
          id: "public-reader",
          email: "reader@test.local",
          system_role: "user",
          business_role: "public",
          capabilities: [],
          needs_setup: false,
        },
      }),
    );
    await page.goto(`/workspace/${path}`);
    await refreshMockUser(page);
    await expect(page.getByText(message, { exact: true })).toBeVisible();
    await page.locator("[data-sidebar='trigger']").first().click();
    await page
      .locator("[data-sidebar='sidebar']")
      .getByRole("link", {
        name: "文史检索",
        exact: true,
      })
      .click();
    await expect(page).toHaveURL(/\/workspace$/);
    await expect(page.locator("[data-mobile='true']")).toHaveCount(0);
  });
}

test("mobile map navigation survives a failed catalog and supports retry", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await isolateBusinessReads(page);
  let attempts = 0;
  await page.route("**/api/map/catalog", (route) => {
    attempts++;
    return route.fulfill({ status: 503, json: { detail: "地图服务暂不可用" } });
  });
  await page.goto("/workspace/map");
  await expect(
    page.getByText("地图资料暂时无法加载", { exact: true }),
  ).toBeVisible();
  const initialAttempts = attempts;
  await page.getByRole("button", { name: "重新加载", exact: true }).click();
  await expect.poll(() => attempts).toBeGreaterThan(initialAttempts);
  await page.locator("[data-sidebar='trigger']").first().click();
  await page
    .locator("[data-sidebar='sidebar']")
    .getByRole("link", {
      name: "文史检索",
      exact: true,
    })
    .click();
  await expect(page).toHaveURL(/\/workspace$/);
});

test("a denied glossary copy displays an error and printing still works", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async () => {
          throw new Error("Clipboard permission denied");
        },
      },
    });
    window.print = () => {
      document.documentElement.dataset.printed = "true";
    };
  });
  await page.route("**/api/knowledge-graph/gloss", (route) =>
    route.fulfill({
      json: {
        title: "测试展签",
        object_name: null,
        source_title: "测试来源",
        volume: null,
        page: null,
        status: "reading_aid",
        status_label: "阅读辅助",
        gloss: {
          original: "测试原文",
          sentences: [
            {
              original: "测试原文",
              modern: "测试释读",
              keywords: [],
              uncertain_terms: [],
            },
          ],
          notes: [],
        },
      },
    }),
  );
  await page.goto("/workspace/glossary");
  await page.getByRole("button", { name: "生成释读展签" }).click();
  await expect(
    page.getByRole("heading", { name: "测试展签", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "复制展签" }).click();
  await expect(
    page.getByText("复制失败，请手动选择展签内容复制"),
  ).toBeVisible();
  await page.getByRole("button", { name: "打印", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-printed", "true");
  expect(errors).toEqual([]);
});
