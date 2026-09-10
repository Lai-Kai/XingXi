import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test("regular users do not receive source administration actions", async ({
  page,
}) => {
  mockLangGraphAPI(page);

  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "regular-user",
        email: "reader@example.test",
        system_role: "user",
        needs_setup: false,
        oauth_provider: null,
      }),
    }),
  );
  await page.route(/\/api\/source-documents$/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/research-projects", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );

  await page.goto("/workspace/library");
  await expect(page.getByRole("button", { name: "上传文献" })).toBeVisible();
  const authRefresh = page.waitForRequest("**/api/v1/auth/me", {
    timeout: 15_000,
  });
  for (let attempt = 0; attempt < 10; attempt += 1) {
    await page.evaluate(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await page.waitForTimeout(100);
  }
  await authRefresh;

  await expect(page.getByText("仅管理员可管理文献")).toBeVisible({
    timeout: 15_000,
  });
  await expect(
    page.getByRole("button", { name: "上传文献" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /知识版本/ }),
  ).toHaveCount(0);
});
