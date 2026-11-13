import { expect, test } from "@playwright/test";

import { mockLangGraphAPI, MOCK_THREAD_ID } from "./utils/mock-api";

test("business modules share the blue workspace surface", async ({ page }) => {
  test.setTimeout(90_000);
  mockLangGraphAPI(page);
  await page.addInitScript(() => localStorage.setItem("theme", "light"));

  for (const modulePath of [
    "agent",
    "library",
    "projects",
    "glossary",
    "knowledge-graph",
    "name-authority",
    "quality",
    "evaluations",
    "operations",
    "chats",
    "scheduled-tasks",
  ]) {
    await test.step(modulePath, async () => {
      await page.goto(`/workspace/${modulePath}`);
      const surface = page.locator(".xingxi-module").first();
      await expect(surface).toBeVisible();
      await expect(surface).toHaveCSS("color", "rgb(15, 23, 42)");
      await expect(surface).toHaveCSS("background-image", /linear-gradient/);
      await expect
        .poll(() =>
          surface.evaluate((node) =>
            getComputedStyle(node).getPropertyValue("--primary").trim(),
          ),
        )
        .toBe("#2563eb");
    });
  }
});

test("historical answers keep their content and use the shared chat theme", async ({
  page,
}) => {
  mockLangGraphAPI(page, {
    threads: [
      {
        thread_id: MOCK_THREAD_ID,
        title: "历史研究记录",
        messages: [
          { type: "human", id: "theme-human", content: "香溪有哪些古桥？" },
          {
            type: "ai",
            id: "theme-answer",
            content: "请结合地方志中的桥梁条目核对年代。",
          },
        ],
      },
    ],
  });
  await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);
  const answer = page
    .getByTestId("main-message-list")
    .locator("[data-assistant-turn]");
  await expect(answer).toContainText("请结合地方志中的桥梁条目核对年代。");
  await expect(answer).toHaveCSS("border-radius", "20px");
  for (const mode of ["light", "dark"]) {
    await page.evaluate(
      (value) =>
        document.documentElement.classList.toggle("dark", value === "dark"),
      mode,
    );
    await expect(answer.locator(".xingxi-answer-content")).toHaveCSS(
      "color",
      mode === "light" ? "rgb(15, 23, 42)" : "rgb(226, 232, 240)",
    );
    await expect(page.getByTestId("xingxi-chat-surface")).toHaveCSS(
      "background-image",
      /linear-gradient/,
    );
  }
});

test("settings portals share blue controls in both display modes", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  await page.goto("/workspace/chats/new");
  await page
    .locator("[data-sidebar='sidebar']")
    .getByRole("button", { name: "设置", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "设置", exact: true });
  await expect(dialog).toBeVisible();
  for (const mode of ["light", "dark"]) {
    await page.evaluate((value) => {
      document.documentElement.classList.toggle("dark", value === "dark");
    }, mode);
    for (const section of ["账号", "外观", "技能", "工具", "关于"]) {
      await dialog.getByRole("button", { name: section, exact: true }).click();
      await expect(dialog).toHaveCSS(
        "color",
        mode === "light" ? "rgb(15, 23, 42)" : "rgb(226, 232, 240)",
      );
      await expect
        .poll(() =>
          dialog.evaluate((node) =>
            getComputedStyle(node).getPropertyValue("--primary").trim(),
          ),
        )
        .toBe(mode === "light" ? "#2563eb" : "#60a5fa");
    }
  }
});
