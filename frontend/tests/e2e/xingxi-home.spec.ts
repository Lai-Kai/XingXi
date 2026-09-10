import { expect, test } from "@playwright/test";

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
          next_refresh_at: "2026-07-30T00:00:00+08:00",
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

    await expect(page).toHaveURL(/\/workspace\/chats\/new\?mode=pro/);
    await expect(page).toHaveURL(/prompt=/);
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

  test("deep exploration keeps Xingxi fixed and selects ultra mode", async ({
    page,
  }) => {
    await page.goto("/workspace");

    await expect(page.getByText("星羲", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "星羲智能体" })).toHaveCount(
      0,
    );
    await page.getByRole("button", { name: "深度求索" }).click();
    await page.getByLabel("研究问题").fill("核验木渎商号");
    await page.getByRole("button", { name: "开始研究" }).click();

    await expect(page).toHaveURL(/\/workspace\/chats\/new\?mode=ultra/, {
      timeout: 15_000,
    });
    expect(new URL(page.url()).searchParams.has("research_mode")).toBe(false);
  });

  test("feed tabs and personalization settings are interactive", async ({
    page,
  }) => {
    await page.goto("/workspace");

    await page.getByRole("tab", { name: "最新收录" }).click();
    await expect(
      page.getByText("民国时期木渎镇区商号与街巷名称索引"),
    ).toBeVisible();

    await page.getByRole("button", { name: "个性化设置" }).click();
    await expect(page.getByText("关注的研究方向")).toBeVisible();
    await page.getByRole("button", { name: "园林" }).click();
    await expect(page.getByRole("button", { name: "园林" })).toHaveAttribute(
      "aria-pressed",
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
    ).toBeVisible();
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
