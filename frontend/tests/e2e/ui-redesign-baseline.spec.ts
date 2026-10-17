import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const captureDir = process.env.UI_BASELINE_DIR;
const coreRoutes = [
  "/workspace",
  "/workspace/chats/new",
  "/workspace/library",
  "/workspace/projects",
  "/workspace/map",
  "/workspace/knowledge-graph",
];
const viewports = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 360, height: 800 },
];

async function mockBaseline(page: Page) {
  // Explicitly unavailable domain endpoints exercise real error UI; fixtures
  // below provide empty lists. No request reaches a production write endpoint.
  await page.route("**/api/**", (route) =>
    route.fulfill({ status: 503, json: { detail: "基线测试：服务暂不可用" } }),
  );
  mockLangGraphAPI(page);
  await page.route(
    /\/api\/(source-documents|research-projects)(\?|$)/,
    (route) => route.fulfill({ json: [] }),
  );
  await page.route(/\/api\/source-documents\/(library\/)?page(\?|$)/, (route) =>
    route.fulfill({ json: { items: [], next_cursor: null, total: 0 } }),
  );
  await page.route(
    /\/api\/(entities|knowledge-graph\/relations|events)(\?|$)/,
    (route) => route.fulfill({ json: [] }),
  );
  await page.route("**/api/map/catalog", (route) =>
    route.fulfill({
      json: {
        updated_at: "2026-10-15",
        data_notice: "截图基线：空目录测试夹具，不代表生产资料。",
        points: [],
        layers: [],
        events: [],
        trajectories: [],
        routes: [],
      },
    }),
  );
  await page.route("**/api/map/reference-points?**", (route) =>
    route.fulfill({ json: [] }),
  );
}

async function capture(page: Page, route: string, theme = "light") {
  const errors: string[] = [];
  const onError = (error: Error) => errors.push(error.message);
  page.on("pageerror", onError);
  await page.addInitScript(
    (value) => localStorage.setItem("theme", value),
    theme,
  );
  const response = await page.goto(route);
  await page.waitForLoadState("networkidle");
  await expect(page.locator("body")).not.toContainText("Application error");
  // A baseline must retain an existing stuck/loading state as evidence rather
  // than aborting the remaining routes. This is reported, never called passed UI.
  const settled = await expect(page.locator('[aria-busy="true"]'))
    .toHaveCount(0)
    .then(
      () => true,
      () => false,
    );
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>((done) =>
      requestAnimationFrame(() => requestAnimationFrame(() => done())),
    );
  });
  const viewport = page.viewportSize()!;
  const name = `${route.replaceAll("/", "_") || "root"}-${viewport.width}-${theme}`;
  await mkdir(captureDir!, { recursive: true });
  await page.screenshot({
    path: resolve(captureDir!, `${name}.png`),
    animations: "disabled",
  });
  const metadata = await page.evaluate(() => ({
    actualUrl: location.href,
    title: document.title,
    viewport: { width: innerWidth, height: innerHeight },
    documentWidth: document.documentElement.scrollWidth,
    theme: document.documentElement.className,
    alerts: Array.from(document.querySelectorAll('[role="alert"]')).map(
      (node) => node.textContent,
    ),
  }));
  await writeFile(
    resolve(captureDir!, `${name}.json`),
    JSON.stringify(
      {
        requestedRoute: route,
        scenario: "mock-empty-or-unavailable",
        status: response?.status(),
        ...metadata,
        settled,
        pageErrors: errors,
      },
      null,
      2,
    ),
  );
  page.off("pageerror", onError);
  expect(errors, route).toEqual([]);
  expect(response?.status(), route).toBeLessThan(400);
}

test.describe("UI redesign runtime and screenshot baseline", () => {
  test.skip(
    !captureDir,
    "Opt-in capture: set UI_BASELINE_DIR to a new evidence directory.",
  );
  for (const viewport of viewports) {
    test(`core routes at ${viewport.width}px`, async ({ page }) => {
      test.setTimeout(120_000);
      await page.setViewportSize(viewport);
      await mockBaseline(page);
      for (const route of coreRoutes) await capture(page, route);
      if (viewport.width === 1440 || viewport.width === 390) {
        for (const route of coreRoutes) await capture(page, route, "dark");
      }
    });
  }
  test("secondary routes and auth surfaces", async ({ page }) => {
    test.setTimeout(120_000);
    await page.setViewportSize(viewports[0]!);
    await mockBaseline(page);
    for (const route of [
      "/workspace/agent",
      "/workspace/chats",
      "/workspace/glossary",
      "/workspace/name-authority",
      "/workspace/quality",
      "/workspace/evaluations",
      "/workspace/operations",
      "/workspace/scheduled-tasks",
      "/login",
      "/setup",
      "/workspace/agents",
    ])
      await capture(page, route);
  });
  for (const role of ["reader", "researcher"] as const) {
    test(`client capability navigation for ${role}`, async ({ page }) => {
      await page.setViewportSize(viewports[0]!);
      await mockBaseline(page);
      await page.route("**/api/v1/auth/me", (route) =>
        route.fulfill({
          json: {
            id: role,
            email: `${role}@example.test`,
            system_role: "user",
            business_role: role === "reader" ? "public" : "researcher",
            capabilities:
              role === "reader"
                ? ["knowledge:read"]
                : ["knowledge:read", "project:manage"],
            needs_setup: false,
          },
        }),
      );
      await page.goto("/workspace/library");
      await page.waitForLoadState("networkidle");
      const refreshed = page.waitForResponse("**/api/v1/auth/me");
      await page.evaluate(() =>
        document.dispatchEvent(new Event("visibilitychange")),
      );
      await refreshed;
      await expect(page.getByText("仅管理员可管理文献")).toBeVisible();
      await expect(
        page.getByRole("link", { name: "文献库", exact: true }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("link", { name: "Agent 评测", exact: true }),
      ).toHaveCount(0);
      await expect(
        page.getByRole("link", { name: "研究项目", exact: true }),
      ).toHaveCount(role === "researcher" ? 1 : 0);
      await page.screenshot({
        path: resolve(captureDir!, `role-${role}-1440.png`),
      });
    });
  }
});
