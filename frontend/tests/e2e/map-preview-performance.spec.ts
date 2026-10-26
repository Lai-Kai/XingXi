import { expect, test, type Page } from "@playwright/test";

import { coloredPlyFixture, gaussianPlyFixture } from "../fixtures/map-ply";

import { mockLangGraphAPI } from "./utils/mock-api";

const point = {
  id: "pt-preview-performance",
  entity_id: "entity-preview-performance",
  name: "预览软件夹具",
  lon: 120.506,
  lat: 31.253,
  entity_type: "bridge",
  confidence: "exact",
  geometry_type: "point",
  basis: "软件测试",
  coordinate_system: "WGS84",
  dynasties: ["modern"],
  heritage_status: "extant",
  access_status: "verify_before_visit",
  summary: "软件夹具",
  address: "木渎",
  evidence: [],
  start_year: null,
  end_year: null,
  record_kind: "reference",
};

async function openLocal(page: Page) {
  mockLangGraphAPI(page);
  await page.route("**/api/map/catalog", (route) =>
    route.fulfill({
      json: {
        updated_at: "2026-10-25",
        data_notice: "软件测试",
        points: [point],
        layers: [
          {
            id: "osm",
            name: "OSM",
            kind: "base",
            available: true,
            attribution: "© OpenStreetMap contributors",
            source_url: "https://www.openstreetmap.org/copyright",
            tile_url: "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
          },
        ],
        events: [],
        relations: [],
        trajectories: [],
        routes: [],
      },
    }),
  );
  await page.route("**/api/map/reference-points?**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/map/reference-events?**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/map/model-assets/page?**", (route) =>
    route.fulfill({ json: { data: [], next_cursor: null } }),
  );
  await page.route("**/api/reconstructions?**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("https://tile.openstreetmap.de/**", (route) =>
    route.fulfill({
      contentType: "image/png",
      body: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        "base64",
      ),
    }),
  );
  await page.goto("/workspace/map");
  const marker = page.getByRole("button", {
    name: new RegExp(`地图点位 ${point.name}`),
  });
  await marker.focus();
  await marker.press("Enter");
  await page.getByRole("tab", { name: "三维预览", exact: true }).click();
}

async function browserFrames(page: Page, count = 20) {
  await page.evaluate(
    (n) =>
      new Promise<void>((resolve) => {
        let left = n;
        const tick = () => {
          if (--left <= 0) resolve();
          else requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      }),
    count,
  );
}

test("RGB worker preview limits points, sleeps when idle, restores full precision and releases the canvas", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await openLocal(page);
  await page.getByLabel("打开本地 PLY").setInputFiles({
    name: "rgb-400001.ply",
    mimeType: "application/octet-stream",
    buffer: Buffer.from(coloredPlyFixture(400_001)),
  });
  const canvas = page.getByLabel("彩色点云三维场景");
  await expect(canvas).toBeVisible({ timeout: 45000 });
  await expect(canvas).toHaveAttribute("data-parse-thread", "worker");
  await expect(canvas).toHaveAttribute("data-source-point-count", "400001");
  await expect(canvas).toHaveAttribute("data-render-point-count", "300000");
  await expect(canvas).toHaveAttribute("data-render-state", "idle");
  const idleFrames = await canvas.getAttribute("data-render-frames");
  await browserFrames(page);
  await expect(canvas).toHaveAttribute("data-render-frames", idleFrames!);
  await canvas.screenshot({ path: testInfo.outputPath("rgb-light.png") });
  await page.getByLabel("PLY 预览精度").selectOption("full");
  await expect(canvas).toHaveAttribute("data-render-point-count", "400001", {
    timeout: 45000,
  });
  await expect(canvas).toHaveAttribute("data-render-state", "idle");
  await page.getByLabel("使用文件透明度").check();
  await page.getByRole("button", { name: "翻转上下", exact: true }).click();
  await page.getByRole("button", { name: "放大查看点云", exact: true }).click();
  await expect(
    page.getByRole("dialog").getByLabel("彩色点云三维场景"),
  ).toBeVisible();
  await expect(canvas).toHaveCount(1);
  await page.getByRole("button", { name: "返回点位详情", exact: true }).click();
  await page.getByRole("tab", { name: "史料考据", exact: true }).click();
  await expect(canvas).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("complete Gaussian fixture renders asynchronous Spark output then goes idle", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await openLocal(page);
  await page.getByLabel("打开本地 PLY").setInputFiles({
    name: "gaussian.ply",
    mimeType: "application/octet-stream",
    buffer: Buffer.from(gaussianPlyFixture()),
  });
  const canvas = page.getByLabel("高斯三维场景");
  await expect(page.getByText(/拖动旋转 · 滚轮缩放/)).toBeVisible({
    timeout: 45000,
  });
  await expect(canvas).toHaveAttribute("data-source-point-count", "128");
  await expect(canvas).toHaveAttribute("data-render-state", "idle", {
    timeout: 30000,
  });
  // Spark may wake once more with an asynchronous sort after the first idle.
  // Require a real stable idle window after those results, without freezing them.
  await expect
    .poll(
      async () => {
        const frames = await canvas.getAttribute("data-render-frames");
        await browserFrames(page, 60);
        return (
          frames === (await canvas.getAttribute("data-render-frames")) &&
          (await canvas.getAttribute("data-render-state")) === "idle"
        );
      },
      { timeout: 10000 },
    )
    .toBe(true);
  await canvas.screenshot({ path: testInfo.outputPath("gaussian.png") });
  await page.getByRole("tab", { name: "史料考据", exact: true }).click();
  await expect(canvas).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("map light preference persists across reload and retains OSM attribution", async ({
  page,
}) => {
  await openLocal(page);
  // The narrow point detail is a modal Sheet; return to the map tools first.
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "地图图层", exact: true }).click();
  await page
    .getByRole("checkbox", { name: "地图流畅模式", exact: true })
    .check();
  await expect(page.locator("[data-map-engine]")).toHaveAttribute(
    "data-map-pixel-ratio",
    "1",
  );
  await page.reload();
  await expect(page.locator("[data-map-engine]")).toHaveAttribute(
    "data-map-performance-mode",
    "light",
  );
  await expect(page.locator("[data-map-engine]")).toHaveAttribute(
    "data-map-pixel-ratio",
    "1",
  );
  await expect(page.locator(".maplibregl-ctrl-attrib-inner")).toContainText(
    "OpenStreetMap contributors",
  );
});
