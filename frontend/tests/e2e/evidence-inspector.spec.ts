import { expect, test } from "@playwright/test";

import {
  MOCK_THREAD_ID,
  MOCK_THREAD_ID_2,
  mockLangGraphAPI,
} from "./utils/mock-api";

for (const width of [1440, 390]) {
  test(`inspect citations without leaving the conversation at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    mockLangGraphAPI(page, {
      threads: [
        {
          thread_id: MOCK_THREAD_ID,
          title: "出处核对",
          messages: [
            { type: "human", id: "question", content: "请核对木渎史料" },
            {
              type: "ai",
              id: "answer",
              content:
                "史料线索[citation:方志卷一](evidence://test-one)。再次引用[citation:方志卷一](evidence://test-one)。",
            },
            {
              type: "ai",
              id: "hidden",
              content: "[citation:隐藏](evidence://hidden)",
              additional_kwargs: { hide_from_ui: true },
            },
          ],
        },
      ],
    });
    let reads = 0;
    await page.route("**/api/knowledge-search/evidence/*", (route) => {
      reads++;
      return route.fulfill({
        json: {
          evidence_id: "test-one",
          document_id: "test-document",
          document_title: "测试方志",
          edition: "测试版",
          volume: "卷一",
          page_start: 1,
          page_end: 2,
          source_level: "U",
          review_status: "pending",
          quote: "仅用于软件回归的合成原文。",
          source_file_id: null,
        },
      });
    });
    await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);
    const messages = page.getByTestId("main-message-list");
    const citation = messages.locator('a[data-evidence-id="test-one"]').first();
    await expect(citation).toBeVisible();
    expect(reads).toBe(0);

    await page.getByRole("button", { name: "史料考据", exact: true }).click();
    const inspector =
      width >= 1280
        ? page.getByRole("complementary", { name: "史料考据视窗", exact: true })
        : page.getByRole("dialog", { name: "史料考据视窗", exact: true });
    await expect(inspector).toContainText("已识别 1 项引用");
    await expect(inspector).toContainText("引用 2 次");
    await expect(inspector.getByText("隐藏", { exact: true })).toHaveCount(0);
    expect(reads).toBe(0);
    await inspector
      .getByRole("button", { name: "关闭史料考据视窗", exact: true })
      .click();

    await citation.click();
    await expect(page).toHaveURL(
      new RegExp(`/workspace/chats/${MOCK_THREAD_ID}$`),
    );
    await expect(inspector).toContainText("仅用于软件回归的合成原文。");
    await expect(inspector).toContainText("U级 / 待复核");
    expect(reads).toBe(1);
    await inspector.getByRole("button", { name: "返回本次对话出处" }).click();
    await expect(inspector).toContainText("已识别 1 项引用");
    await inspector
      .getByRole("button", { name: "方志卷一", exact: true })
      .click();
    await expect(inspector).toContainText("测试方志");
    await inspector
      .getByRole("button", { name: "关闭史料考据视窗", exact: true })
      .click();
    await expect(inspector).toBeHidden();
  });
}

test("an unavailable citation keeps the conversation usable and can be reopened", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  mockLangGraphAPI(page, {
    threads: [
      {
        thread_id: MOCK_THREAD_ID,
        title: "出处暂不可用",
        messages: [
          {
            type: "ai",
            id: "answer",
            content: "[citation:方志](evidence://unavailable)",
          },
        ],
      },
      {
        thread_id: MOCK_THREAD_ID_2,
        title: "另一项研究",
        messages: [{ type: "ai", id: "another-answer", content: "尚待研究" }],
      },
    ],
  });
  await page.route("**/api/knowledge-search/evidence/*", (route) =>
    route.fulfill({
      status: 403,
      json: { detail: "该史料当前无权访问" },
    }),
  );
  await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);
  const citation = page
    .getByTestId("main-message-list")
    .locator('a[data-evidence-id="unavailable"]');
  await citation.click();
  const inspector = page.getByRole("complementary", {
    name: "史料考据视窗",
    exact: true,
  });
  await expect(inspector).toContainText("确认访问权限");
  await expect(inspector).not.toContainText("evidence://");
  await page.keyboard.press("Escape");
  await expect(inspector).toBeHidden();
  await expect(citation).toBeFocused();
  await citation.click();
  await expect(inspector).toContainText("确认访问权限");
  await expect(inspector).not.toContainText("evidence://");
  await page.getByRole("link", { name: "另一项研究", exact: true }).click();
  await expect(page).toHaveURL(
    new RegExp(`/workspace/chats/${MOCK_THREAD_ID_2}$`),
  );
  await expect(inspector).toBeHidden();
  await page.getByRole("button", { name: "史料考据", exact: true }).click();
  await expect(
    page.getByRole("complementary", { name: "史料考据视窗", exact: true }),
  ).toContainText("等待一条可核验的引文");
});
