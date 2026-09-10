import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const THREAD_ID = "00000000-0000-0000-0000-0000000000f1";
const RUN_ID = `run-${THREAD_ID}`;

test("users can rate an answer and submit a categorized problem", async ({
  page,
}) => {
  mockLangGraphAPI(page, {
    threads: [
      {
        thread_id: THREAD_ID,
        title: "反馈测试会话",
        updated_at: "2026-08-15T10:00:00Z",
        messages: [
          {
            type: "human",
            id: "question-1",
            content: [{ type: "text", text: "范仲淹是否到过木渎？" }],
          },
          {
            type: "ai",
            id: "answer-1",
            run_id: RUN_ID,
            content: "范仲淹曾到访木渎，但这条回答需要进一步核对出处。",
          },
        ],
      },
    ],
  });

  const submissions: Array<Record<string, unknown>> = [];
  let deleteCount = 0;
  await page.route(
    `**/api/threads/${THREAD_ID}/runs/${RUN_ID}/feedback`,
    async (route) => {
      if (route.request().method() === "DELETE") {
        deleteCount += 1;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ success: true }),
        });
      }
      const body = route.request().postDataJSON() as Record<string, unknown>;
      submissions.push(body);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          feedback_id: `feedback-${submissions.length}`,
          thread_id: THREAD_ID,
          run_id: RUN_ID,
          user_id: "default",
          rating: body.rating,
          comment: body.comment,
          category: body.category,
          status: "submitted",
          created_at: "2026-08-15T10:01:00Z",
        }),
      });
    },
  );

  await page.goto(`/workspace/chats/${THREAD_ID}`);
  await expect(page.getByText("这个回答有帮助吗？")).toBeVisible({
    timeout: 15_000,
  });

  const helpful = page.getByRole("button", { name: "回答有帮助" });
  await helpful.click();
  await expect(helpful).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("已记录")).toBeVisible();
  expect(submissions[0]).toMatchObject({
    rating: 1,
    comment: null,
    category: null,
  });

  await helpful.click();
  await expect(helpful).toHaveAttribute("aria-pressed", "false");
  expect(deleteCount).toBe(1);

  await page.getByRole("button", { name: "反馈回答问题" }).click();
  await expect(
    page.getByRole("dialog", { name: "反馈回答问题" }),
  ).toBeVisible();
  await page.getByLabel("问题类型").selectOption("citation_error");
  await page.getByLabel("问题说明").fill("引用页码与原文不一致，请复核。");
  await page.getByRole("button", { name: "提交反馈" }).click();

  await expect(page.getByRole("dialog", { name: "反馈回答问题" })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole("button", { name: "反馈回答问题" }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(submissions[1]).toMatchObject({
    rating: -1,
    category: "citation_error",
    comment: "引用页码与原文不一致，请复核。",
  });
});
