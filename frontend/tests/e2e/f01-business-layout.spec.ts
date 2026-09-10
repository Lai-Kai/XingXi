import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const businessRoutes = [
  "/workspace",
  "/workspace/agent",
  "/workspace/library",
  "/workspace/projects",
  "/workspace/map",
];

const viewports = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
];

test("business pages do not create document-level horizontal overflow", async ({
  page,
}) => {
  test.setTimeout(90_000);
  mockLangGraphAPI(page);

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);

    for (const route of businessRoutes) {
      await page.goto(route);
      await expect(page.locator("main").first()).toBeVisible({
        timeout: 15_000,
      });

      const dimensions = await page.evaluate(() => ({
        viewportWidth: window.innerWidth,
        bodyWidth: document.body.scrollWidth,
        documentWidth: document.documentElement.scrollWidth,
      }));

      expect(dimensions, `${route} at ${viewport.width}px`).toEqual({
        viewportWidth: viewport.width,
        bodyWidth: viewport.width,
        documentWidth: viewport.width,
      });
    }
  }
});
