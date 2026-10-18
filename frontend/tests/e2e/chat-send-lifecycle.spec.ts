import { expect, test } from "@playwright/test";

import { handleRunStream, mockLangGraphAPI } from "./utils/mock-api";

test("first send keeps its conversation and the next message uses the same thread", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  const errors: string[] = [];
  const runPaths: string[] = [];
  let threadCreates = 0;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/langgraph/threads"
    ) {
      threadCreates++;
    }
  });
  await page.route("**/runs/stream", (route) => {
    runPaths.push(new URL(route.request().url()).pathname);
    return handleRunStream(route);
  });

  await page.goto("/workspace/chats/new");
  const composer = page.locator("textarea").first();
  const messages = page.getByTestId("main-message-list");
  await expect(composer).toBeVisible();
  await composer.fill("介绍一下木渎");
  await composer.press("Enter");

  await expect(page).toHaveURL(/\/workspace\/chats\/[0-9a-f-]{36}$/);
  const conversationPath = new URL(page.url()).pathname;
  await expect(messages.getByText("Hello from DeerFlow!")).toBeVisible();
  await expect(composer).toBeEnabled();
  await expect(
    page
      .getByRole("button", { name: "Submit", exact: true })
      .locator(".lucide-arrow-up"),
  ).toBeVisible();

  await composer.fill("再介绍一下灵岩山");
  await composer.press("Enter");
  await expect.poll(() => runPaths.length).toBe(2);
  expect(runPaths).toEqual([
    `/api/langgraph/threads/${conversationPath.split("/").at(-1)}/runs/stream`,
    runPaths[0],
  ]);
  await expect(page).toHaveURL(new RegExp(`${conversationPath}$`));
  expect(threadCreates).toBe(1);
  expect(errors).toEqual([]);
});
