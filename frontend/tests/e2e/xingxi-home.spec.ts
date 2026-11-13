import { expect, test } from "@playwright/test";

import type { DailyResearchFeed } from "../../src/core/research-feed/api";

import { mockLangGraphAPI } from "./utils/mock-api";

test.describe("Xingxi home", () => {
  test.beforeEach(async ({ page }) => {
    mockLangGraphAPI(page);
    await page.route("**/api/research-feed/daily?**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          kind: "daily_grounded",
          generated_for: "2026-07-29",
          next_refresh_at: "2099-07-30T00:00:00+08:00",
          items: [
            {
              id: "daily-bridge",
              title: "木渎古桥名称沿革",
              summary: "核对方志、碑刻中的桥名与位置变化。",
              tag: "古迹考证",
              source_basis: "已发布历史文献",
              prompt: "考证木渎古桥名称沿革",
              retrieval_query: "木渎 古桥",
              origin: "evidence_backed_fallback",
              evidence_count: 4,
              knowledge_release_id: "release-1",
              popularity_users: null,
              popularity_searches: null,
              sources: [
                {
                  evidence_id: "evidence-bridge",
                  document_id: "document-bridge",
                  document_title: "（康熙）吴县志",
                  chunk_id: "chunk-bridge",
                  page_start: 12,
                  page_end: 13,
                  quote: "木渎桥梁原文",
                },
              ],
            },
          ],
        }),
      });
    });
  });

  test("research composer opens the Xingxi chat workspace", async ({
    page,
  }) => {
    await page.goto("/workspace");

    await page.getByLabel("研究问题").fill("香溪沿岸有哪些古桥？");
    await page.getByRole("button", { name: "开始研究" }).click();

    const destination = new URL(page.url());
    expect(destination.pathname).toBe("/workspace/chats/new");
    expect(destination.searchParams.has("mode")).toBe(false);
    expect(destination.searchParams.get("prompt")).toBe("香溪沿岸有哪些古桥？");
    await expect(
      page.getByRole("textbox", {
        name: /询问木渎古迹、人物、方志出处或历史沿革|Ask about Mudu sites, people, gazetteers, or historical change/,
      }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole("status").filter({
        hasText: /尚未配置对话模型|No chat model is configured/,
      }),
    ).toBeVisible();
  });

  for (const legacyMode of ["pro", "flash", "ultra"] as const) {
    test(`legacy ${legacyMode} URL opens the canonical chat page`, async ({
      page,
    }) => {
      await page.goto(
        `/workspace/chats/new?mode=${legacyMode}&prompt=%E6%A0%B8%E9%AA%8C%E6%9C%A8%E6%B8%8E%E5%95%86%E5%8F%B7`,
      );

      const destination = new URL(page.url());
      expect(destination.pathname).toBe("/workspace/chats/new");
      expect(destination.searchParams.has("mode")).toBe(false);
      expect(destination.searchParams.get("prompt")).toBe("核验木渎商号");
      await expect(
        page.getByRole("textbox", {
          name: /询问木渎古迹、人物、方志出处或历史沿革|Ask about Mudu sites, people, gazetteers, or historical change/,
        }),
      ).toBeVisible({ timeout: 15_000 });
    });
  }

  test("the canonical agent entry clears stale project scope", async ({
    page,
  }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "deerflow.local-settings",
        JSON.stringify({
          context: {
            mode: "ultra",
            reasoning_effort: "high",
            research_project_id: "stale-project",
            research_project_name: "旧研究项目",
            research_project_document_ids: ["stale-document"],
          },
        }),
      );
    });

    await page.goto("/workspace/agent");
    await expect(page.getByRole("link", { name: "启动专业研究" })).toHaveCount(
      0,
    );
    await expect(page.getByRole("link", { name: "启动轻量问答" })).toHaveCount(
      0,
    );
    const entryLink = page.getByRole("link", { name: "开始对话" });
    await expect(entryLink).toHaveAttribute("href", "/workspace/chats/new");
    await entryLink.click();

    await expect(page).toHaveURL(/\/workspace\/chats\/new$/);
    await expect(
      page.getByRole("textbox", {
        name: /询问木渎古迹、人物、方志出处或历史沿革|Ask about Mudu sites, people, gazetteers, or historical change/,
      }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("对话页面暂时无法加载")).toHaveCount(0);

    await expect
      .poll(() =>
        page.evaluate(() => {
          const stored = window.localStorage.getItem("deerflow.local-settings");
          return stored
            ? (JSON.parse(stored) as { context?: Record<string, unknown> })
                .context
            : undefined;
        }),
      )
      .toEqual({
        mode: "ultra",
        reasoning_effort: "high",
      });
    expect(pageErrors).toEqual([]);
  });

  test("the configured model selector owns the model difference", async ({
    page,
  }) => {
    let submittedContext: Record<string, unknown> | undefined;
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url().includes("/runs/stream")
      ) {
        submittedContext = (
          request.postDataJSON() as {
            context?: Record<string, unknown>;
          }
        ).context;
      }
    });
    await page.route("**/api/models", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          models: [
            {
              id: "quick-model",
              name: "quick-model",
              model: "quick-model",
              display_name: "轻量模型",
              supports_thinking: false,
              supports_reasoning_effort: false,
            },
            {
              id: "research-model",
              name: "research-model",
              model: "research-model",
              display_name: "研究模型",
              supports_thinking: true,
              supports_reasoning_effort: true,
            },
          ],
          token_usage: { enabled: false },
        }),
      }),
    );

    await page.goto("/workspace/agent");
    await page.getByRole("link", { name: "开始对话" }).click();
    await expect(page).toHaveURL(/\/workspace\/chats\/new$/);
    await page.getByRole("button", { name: "轻量模型" }).click();
    await page.getByRole("option", { name: /研究模型/ }).click();

    const textarea = page.getByRole("textbox", {
      name: /询问木渎古迹、人物、方志出处或历史沿革|Ask about Mudu sites, people, gazetteers, or historical change/,
    });
    await textarea.fill("验证模型选择");
    await textarea.press("Enter");

    await expect(page.getByText("Hello from DeerFlow!")).toBeVisible({
      timeout: 10_000,
    });
    await expect
      .poll(() => submittedContext)
      .toMatchObject({
        model_name: "research-model",
      });
  });

  test("a current research project replaces the previously stored scope", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "deerflow.local-settings",
        JSON.stringify({
          context: {
            research_project_id: "stale-project",
            research_project_name: "旧研究项目",
            research_project_document_ids: ["stale-document"],
          },
        }),
      );
    });
    await page.route("**/api/research-projects/current-project", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "current-project",
          name: "当前研究项目",
          archived: false,
          document_count: 1,
          created_at: "2026-09-13T00:00:00+08:00",
          updated_at: "2026-09-13T00:00:00+08:00",
        }),
      }),
    );
    await page.route(
      "**/api/research-projects/current-project/documents",
      (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([{ id: "current-document" }]),
        }),
    );

    await page.goto("/workspace/chats/new?project_id=current-project");
    await expect(
      page.getByRole("textbox", {
        name: /询问木渎古迹、人物、方志出处或历史沿革|Ask about Mudu sites, people, gazetteers, or historical change/,
      }),
    ).toBeVisible({ timeout: 15_000 });
    await expect
      .poll(() =>
        page.evaluate(() => {
          const stored = window.localStorage.getItem("deerflow.local-settings");
          return stored
            ? (JSON.parse(stored) as { context?: Record<string, unknown> })
                .context
            : undefined;
        }),
      )
      .toMatchObject({
        research_project_id: "current-project",
        research_project_name: "当前研究项目",
        research_project_document_ids: ["current-document"],
      });
  });

  test("document leads and collections use the actual daily sources", async ({
    page,
  }) => {
    await page.goto("/workspace");

    await expect(
      page.getByRole("link", { name: "木渎古桥名称沿革", exact: true }),
    ).toBeVisible();
    await page.getByRole("tab", { name: "文献线索" }).click();
    await expect(
      page.getByRole("heading", { name: "（康熙）吴县志" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "12–13页 · 查看原文" }),
    ).toBeVisible();
    await page.getByRole("tab", { name: "专题阅读" }).click();
    await expect(page.getByRole("heading", { name: "古迹考证" })).toBeVisible();
    await expect(
      page.getByRole("link", { name: "木渎古桥名称沿革", exact: true }),
    ).toHaveAttribute("href", /evidence_id=evidence-bridge/);
    await page.getByRole("tab", { name: "专题阅读" }).press("Home");
    await expect(page.getByRole("tab", { name: "今日选题" })).toBeFocused();
    await page.getByRole("tab", { name: "今日选题" }).press("ArrowRight");
    await expect(page.getByRole("tab", { name: "文献线索" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  test("daily topics come from the current backend feed", async ({ page }) => {
    await page.goto("/workspace");

    await expect(page.getByRole("tab", { name: "今日选题" })).toBeVisible();
    await expect(page.getByText("2026-07-29")).toBeVisible();
    await expect(page.getByText("木渎古桥名称沿革")).toBeVisible();
    await expect(page.getByText("2026-07-18")).toHaveCount(0);

    const href = await page
      .getByRole("link", { name: "开始了解" })
      .getAttribute("href");
    const url = new URL(href ?? "", "http://localhost");
    expect(url.searchParams.get("topic_query")).toBe("木渎 古桥");
    expect(url.searchParams.getAll("document_id")).toEqual(["document-bridge"]);
    expect(url.searchParams.getAll("evidence_id")).toEqual(["evidence-bridge"]);
  });

  test("quick questions stay editable and source preferences travel with the query", async ({
    page,
  }) => {
    await page.goto("/workspace");
    await expect(page.getByRole("button", { name: "开始研究" })).toBeDisabled();
    await page.getByRole("button", { name: /人物与地方记忆/ }).click();
    const input = page.getByLabel("研究问题");
    await expect(input).toBeFocused();
    await expect(input).toHaveValue(/范仲淹/);
    await input.fill("香溪沿岸有哪些古桥？");
    await page.getByRole("button", { name: "地方志", exact: true }).click();
    const inscriptions = page.getByRole("button", {
      name: "碑刻拓片",
      exact: true,
    });
    await inscriptions.click();
    await expect(inscriptions).toHaveAttribute("aria-pressed", "true");
    await inscriptions.click();
    await expect(inscriptions).toHaveAttribute("aria-pressed", "false");
    await page.getByRole("button", { name: "开始研究" }).click();
    expect(new URL(page.url()).searchParams.get("prompt")).toBe(
      "香溪沿岸有哪些古桥？\n\n优先查阅：地方志。请注明出处与页码。",
    );
  });

  test("Chinese composition Enter does not submit and Shift+Enter keeps a multiline draft", async ({
    page,
  }) => {
    await page.goto("/workspace");
    const input = page.getByLabel("研究问题");
    await input.fill("木渎古桥");
    await input.dispatchEvent("keydown", {
      key: "Enter",
      code: "Enter",
      keyCode: 229,
      isComposing: true,
    });
    await expect(page).toHaveURL(/\/workspace$/);
    await input.press("End");
    await input.press("Shift+Enter");
    await input.pressSequentially("出处");
    await expect(input).toHaveValue("木渎古桥\n出处");
    await input.press("Enter");
    await expect(page).toHaveURL(/\/workspace\/chats\/new\?/);
  });

  test("source preview loads the selected Evidence and closes with keyboard focus restored", async ({
    page,
  }) => {
    await page.route(
      "**/api/knowledge-search/evidence/evidence-bridge",
      (route) =>
        route.fulfill({
          json: {
            evidence_id: "evidence-bridge",
            document_id: "document-bridge",
            chunk_id: "chunk-bridge",
            source_file_id: null,
            document_title: "（康熙）吴县志",
            edition: "康熙刻本",
            volume: "卷一",
            section: "桥梁",
            page_start: 12,
            page_end: 13,
            folio_start: null,
            folio_end: null,
            quote: "完整桥梁原文与上下文",
            source_level: "A",
            review_status: "reviewed",
            href: "evidence://evidence-bridge",
          },
        }),
    );
    await page.goto("/workspace");
    const preview = page.getByRole("button", {
      name: "查看原文：（康熙）吴县志",
      exact: true,
    });
    await preview.click();
    const sheet = page.getByRole("dialog", { name: "原文与出处" });
    await expect(sheet).toBeVisible();
    await expect(
      sheet.getByText("木渎桥梁原文", { exact: true }),
    ).toBeVisible();
    await expect(
      sheet.getByText("完整桥梁原文与上下文", { exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    await expect(preview).toBeFocused();
  });

  test("failed Evidence loading keeps the feed excerpt available", async ({
    page,
  }) => {
    await page.route(
      "**/api/knowledge-search/evidence/evidence-bridge",
      (route) => route.fulfill({ status: 503, json: { detail: "暂时不可用" } }),
    );
    await page.goto("/workspace");
    await page
      .getByRole("button", { name: "查看原文：（康熙）吴县志", exact: true })
      .click();
    const sheet = page.getByRole("dialog", { name: "原文与出处" });
    await expect(sheet.getByText("暂无法打开该资料出处详情")).toBeVisible();
    await expect(
      sheet.getByText("木渎桥梁原文", { exact: true }),
    ).toBeVisible();
  });

  test("the highlighted sidebar entry opens the agent module once", async ({
    page,
  }) => {
    await page.goto("/workspace");
    const entry = page.getByRole("link", { name: "星羲智能体", exact: true });
    await expect(entry).toHaveCount(1);
    await expect(entry).toHaveAttribute("href", "/workspace/agent");
    await expect(
      page.getByRole("button", { name: "新建检索项目", exact: true }),
    ).toHaveCount(0);
    await entry.click();
    await expect(page).toHaveURL(/\/workspace\/agent$/);
    await expect(entry).toHaveAttribute("aria-current", "page");
    await expect(
      page.getByRole("link", { name: "开始对话", exact: true }),
    ).toBeVisible();
  });

  test("more topics expand in place and retain the original dated source scope", async ({
    page,
  }) => {
    const pending = page.waitForResponse((response) =>
      response.url().includes("/api/research-feed/daily?"),
    );
    await page.goto("/workspace");
    const feed = (await (await pending).json()) as DailyResearchFeed;
    await page.route("**/api/research-feed/history?days=7", (route) =>
      route.fulfill({
        json: {
          kind: "daily_grounded_history",
          current: feed,
          previous: [
            {
              ...feed,
              generated_for: "2026-07-28",
              items: [{ ...feed.items[0], title: "往日桥梁选题" }],
            },
          ],
          history_days: 7,
        },
      }),
    );
    await page.getByRole("button", { name: "查看更多今日与往日选题" }).click();
    await expect(page).toHaveURL(/\/workspace$/);
    await expect(
      page.getByRole("link", { name: "往日桥梁选题", exact: true }),
    ).toHaveAttribute("href", /evidence_id=evidence-bridge/);
    await page.getByRole("button", { name: "收起更多选题" }).click();
    await expect(
      page.getByRole("link", { name: "往日桥梁选题", exact: true }),
    ).toHaveCount(0);
  });

  test("mobile home keeps the composer in the viewport and opens navigation", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/workspace");
    await expect(
      page.getByRole("heading", { name: "今天想查阅哪一段木渎历史？" }),
    ).toBeVisible();
    const input = page.getByLabel("研究问题");
    const box = await input.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(390);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.locator("[data-sidebar='trigger']:visible").first().click();
    await expect(
      page.locator("[data-mobile='true'][data-sidebar='sidebar']"),
    ).toBeVisible();
    await page.getByRole("link", { name: "星羲智能体", exact: true }).click();
    await expect(page).toHaveURL(/\/workspace\/agent$/);
    await expect(
      page.locator("[data-mobile='true'][data-sidebar='sidebar']"),
    ).not.toBeVisible();
  });

  for (const entry of ["木渎古桥名称沿革", "开始了解"]) {
    test(`daily topic ${entry} starts a scoped Xingxi answer automatically`, async ({
      page,
    }) => {
      const errors: string[] = [];
      const submissions: Array<{
        assistant_id: string;
        context: Record<string, unknown>;
        input: { messages: Array<{ content: Array<{ text: string }> }> };
      }> = [];
      page.on("pageerror", (error) => errors.push(error.message));
      page.on("request", (request) => {
        if (
          request.method() === "POST" &&
          request.url().includes("/runs/stream")
        ) {
          submissions.push(
            request.postDataJSON() as (typeof submissions)[number],
          );
        }
      });
      await page.route("**/api/models", (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            models: [
              {
                id: "test-model",
                name: "test-model",
                model: "test-model",
                display_name: "测试模型",
                supports_thinking: false,
              },
            ],
            token_usage: { enabled: false },
          }),
        }),
      );

      await page.goto("/workspace");
      await page.getByRole("link", { name: entry, exact: true }).click();

      await expect(
        page.getByTestId("main-message-list").getByText("Hello from DeerFlow!"),
      ).toBeVisible();
      await expect(page).toHaveURL(/\/workspace\/chats\/[0-9a-f-]{36}$/);
      expect(submissions).toHaveLength(1);
      expect(submissions[0]?.assistant_id).toBe("xingxi");
      expect(submissions[0]?.context).toMatchObject({
        daily_topic_query: "木渎 古桥",
        daily_topic_document_ids: ["document-bridge"],
        daily_topic_evidence_ids: ["evidence-bridge"],
      });
      expect(submissions[0]?.input.messages.at(-1)?.content).toEqual([
        { type: "text", text: "考证木渎古桥名称沿革" },
      ]);
      expect(errors).toEqual([]);
    });
  }

  test("daily topics use source-bound local seeds when the API fails", async ({
    page,
  }) => {
    await page.route("**/api/research-feed/daily?**", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "feed unavailable" }),
      });
    });

    await page.goto("/workspace");

    await expect(
      page.getByText("部分内容暂时使用本地资料", { exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByText("地方文献怎样记载朱买臣与吴地的联系？", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "开始了解" })).toHaveCount(6);
    await expect(page.getByText(/资料依据：/)).toHaveCount(6);
  });

  test("the research workspace no longer labels grounded topics as demo data", async ({
    page,
  }) => {
    await page.goto("/workspace");

    await expect(page.getByText("演示数据", { exact: true })).toHaveCount(0);

    await page.goto("/workspace/agent");
    await expect(
      page.getByRole("status").filter({ hasText: "演示数据" }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("研究示例").first()).toBeVisible();
  });

  test("research projects expose a retryable page error", async ({ page }) => {
    await page.route("**/api/research-projects", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "项目服务暂时不可用" }),
      });
    });

    await page.goto("/workspace/projects");

    await expect(page.getByText("暂时无法加载")).toBeVisible();
    await expect(page.getByText("项目服务暂时不可用")).toBeVisible();
    await expect(page.getByRole("button", { name: "重新加载" })).toBeVisible();
  });
});
