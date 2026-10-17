import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test.use({ timezoneId: "Asia/Shanghai" });

for (const locale of ["zh-CN", "en-US"]) {
  test(`map recipes fill localized drafts and create only on explicit submission (${locale})`, async ({
    page,
    context,
  }, testInfo) => {
    await context.addCookies([
      {
        name: "locale",
        value: locale,
        url: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3106",
      },
    ]);
    mockLangGraphAPI(page, { threads: [], scheduledTasks: [] });
    const writes: Record<string, unknown>[] = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        new URL(request.url()).pathname === "/api/scheduled-tasks"
      )
        writes.push(request.postDataJSON());
    });
    await page.goto("/workspace/scheduled-tasks");
    const form = page.getByTestId("scheduled-task-create-form");
    const recipes = form.getByTestId("schedule-recipes");
    await expect(recipes.getByRole("button")).toHaveCount(4);
    await expect(recipes).not.toContainText(
      /GitHub|Trending|tech news|科技新闻/,
    );
    const names =
      locale === "zh-CN"
        ? [
            "每日地图史料线索",
            "地图点位考据",
            "古今地名核对",
            "每周地图研习简报",
          ]
        : [
            "Daily map source notes",
            "Map point evidence review",
            "Historical place-name review",
            "Weekly historical map brief",
          ];
    const title = form.getByPlaceholder(
      locale === "zh-CN" ? "任务标题" : "Task title",
      { exact: true },
    );
    const prompt = form.getByPlaceholder(
      locale === "zh-CN" ? "提示词" : "Prompt",
      { exact: true },
    );
    for (const name of names) {
      await recipes.getByRole("button", { name: new RegExp(name) }).click();
      await expect(title).toHaveValue(name);
      await expect(prompt).toHaveValue(locale === "zh-CN" ? /木渎/ : /Mudu/);
      await expect(prompt).toHaveValue(
        locale === "zh-CN" ? /出处/ : /evidence IDs/,
      );
      await expect(prompt).toHaveValue(
        locale === "zh-CN" ? /不.*(修改|写入|合并)/ : /do not (modify|merge)/,
      );
      expect(writes).toHaveLength(0);
    }
    const submittedPrompt = await prompt.inputValue();
    if (locale === "zh-CN") {
      await page.setViewportSize({ width: 390, height: 844 });
      await form.screenshot({
        path: testInfo.outputPath("map-recipes-mobile.png"),
      });
    }
    await form
      .getByRole("button", {
        name: locale === "zh-CN" ? "创建" : "Create",
        exact: true,
      })
      .click();
    await expect.poll(() => writes.length).toBe(1);
    expect(writes[0]).toMatchObject({
      title: names[3],
      prompt: submittedPrompt,
      schedule_type: "cron",
      schedule_spec: { cron: "0 9 * * 1" },
      timezone: "Asia/Shanghai",
      context_mode: "fresh_thread_per_run",
    });
    await expect(
      page
        .getByTestId("scheduled-task-detail")
        .getByText(submittedPrompt, { exact: true }),
    ).toBeVisible();
  });
}
