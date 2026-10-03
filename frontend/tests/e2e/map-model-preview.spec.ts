import { type ModelViewerElement } from "@google/model-viewer";
import { expect, test, type Page } from "@playwright/test";

import { MAP_MODEL_ASSETS } from "../../src/core/map/model-assets";

import { mockLangGraphAPI } from "./utils/mock-api";

const places = [
  [
    "pt-mudu-old-town",
    "entity-place-mudu-old-town",
    "木渎古镇",
    120.5067399,
    31.2530116,
  ],
  ["pt-hongyin", "entity-garden-hongyin", "虹饮山房", 120.5071229, 31.2535504],
  [
    "pt-gusong-garden",
    "entity-garden-gusong",
    "古松园",
    120.5088972,
    31.2529539,
  ],
  [
    "pt-bangyan-mansion",
    "entity-residence-bangyan",
    "榜眼府第",
    120.5110345,
    31.2501758,
  ],
  [
    "pt-mingyue-temple",
    "entity-temple-mingyue",
    "明月古寺",
    120.5062006,
    31.2538627,
  ],
  [
    "pt-lingyan-temple",
    "entity-temple-lingyan",
    "灵岩山寺",
    120.4971399,
    31.2643302,
  ],
  [
    "pt-yongan-bridge",
    "entity-bridge-yongan",
    "永安桥",
    120.5043797,
    31.2540876,
  ],
  ["pt-yan-garden", "entity-garden-yan", "严家花园", 120.5044475, 31.2547028],
  [
    "pt-lingyan-mountain",
    "entity-landform-lingyan",
    "灵岩山",
    120.497,
    31.2647,
  ],
] as const;

function modelReferences() {
  return places.map(([id, entity_id, name, lon, lat]) => ({
    id,
    entity_id,
    name,
    lon,
    lat,
    entity_type: id === "pt-yongan-bridge" ? "bridge" : "garden",
    confidence: id === "pt-yongan-bridge" ? "approximate" : "exact",
    geometry_type: id === "pt-yongan-bridge" ? "uncertainty_radius" : "point",
    uncertainty_radius_m: id === "pt-yongan-bridge" ? 750 : null,
    basis: "沿用地图关联点位",
    coordinate_system: "WGS84",
    dynasties: ["modern"],
    heritage_status: "extant",
    access_status: "verify_before_visit",
    summary: `${name}测试景点资料`,
    address: "木渎",
    evidence: [],
    start_year: null,
    end_year: null,
    record_kind: "reference",
  }));
}

async function setup(page: Page) {
  mockLangGraphAPI(page);
  await page.route("**/api/operations/events", (route) =>
    route.fulfill({ status: 204 }),
  );
  await page.route("**/api/map/reference-points?**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(modelReferences()),
    }),
  );
  await page.route("**/api/map/catalog", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        updated_at: "2026-10-03",
        data_notice: "浏览器测试目录；模型使用本地真实文件。",
        points: modelReferences(),
        layers: [
          {
            id: "osm-current",
            name: "现代底图",
            kind: "base",
            available: true,
            source_url: "https://www.openstreetmap.org/copyright",
            attribution: "© OpenStreetMap contributors",
            calibration_note: "现代底图",
            tile_url: "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
          },
        ],
        events: [],
        relations: [],
        trajectories: [],
        routes: [],
      }),
    }),
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
}

async function selectModel(page: Page, index: number) {
  const name = places[index]![2];
  const marker = page.getByRole("button", {
    name: new RegExp(`地图(?:点位|范围) ${name}，可预览三维模型`),
  });
  // Keyboard selection avoids overlap between nearby real map coordinates.
  await marker.focus();
  await marker.press("Enter");
  await expect(
    page.getByRole("tab", { name: "模型", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
}

async function ready(page: Page, index: number) {
  const asset = MAP_MODEL_ASSETS[index]!;
  await expect(page.locator(`[data-model-id="${asset.id}"]`)).toHaveAttribute(
    "data-model-state",
    "ready",
    { timeout: 120_000 },
  );
  await expect(page.locator("model-viewer")).toHaveCount(1);
  expect(
    await page
      .locator("model-viewer")
      .evaluate(
        (element) =>
          new URL(element.getAttribute("src")!, window.location.href).pathname,
      ),
  ).toBe(asset.src);
  await expect
    .poll(async () =>
      page
        .locator("model-viewer")
        .evaluate((element) => (element as ModelViewerElement).loaded),
    )
    .toBe(true);
}

test("all seven real GLBs render on demand and reuse one viewer for enlargement", async ({
  page,
}, testInfo) => {
  test.setTimeout(480_000);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await setup(page);
  const requests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith(".glb"))
      requests.push(request.url());
  });
  await page.goto("/workspace/map");
  await expect(page.locator('[data-model-badge="true"]')).toHaveCount(7);
  await expect(page.locator('[data-has-model="false"]')).toHaveCount(2);
  expect(requests).toHaveLength(0);
  const timings: Array<{ id: string; milliseconds: number }> = [];
  for (let i = 0; i < 7; i++) {
    const started = Date.now();
    await selectModel(page, i);
    await ready(page, i);
    timings.push({
      id: MAP_MODEL_ASSETS[i]!.id,
      milliseconds: Date.now() - started,
    });
    await page
      .getByRole("region", { name: "三维模型预览" })
      .screenshot({ path: testInfo.outputPath(`model-${i}.png`) });
    await page.locator("model-viewer").evaluate((element) => {
      const model = element as ModelViewerElement;
      model.cameraOrbit = "0deg 75deg 105%";
      model.jumpCameraToGoal();
    });
    await expect
      .poll(async () =>
        page
          .locator("model-viewer")
          .evaluate(
            (element) => (element as ModelViewerElement).getCameraOrbit().theta,
          ),
      )
      .toBeCloseTo(0, 3);
    await page
      .getByRole("region", { name: "三维模型预览" })
      .screenshot({ path: testInfo.outputPath(`model-${i}-side.png`) });
    await page.getByRole("button", { name: "复位", exact: true }).click();
  }
  await testInfo.attach("real-model-timings", {
    body: JSON.stringify(timings, null, 2),
    contentType: "application/json",
  });
  const viewer = page.locator("model-viewer");
  const initial = await viewer.evaluate((element) =>
    (element as ModelViewerElement).getCameraOrbit(),
  );
  const box = (await viewer.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    box.x + box.width / 2 + 50,
    box.y + box.height / 2 + 15,
    { steps: 10 },
  );
  await page.mouse.up();
  await expect
    .poll(async () =>
      viewer.evaluate(
        (element) => (element as ModelViewerElement).getCameraOrbit().theta,
      ),
    )
    .not.toBe(initial.theta);
  const radius = await viewer.evaluate(
    (element) => (element as ModelViewerElement).getCameraOrbit().radius,
  );
  await page.mouse.wheel(0, -160);
  await expect
    .poll(async () =>
      viewer.evaluate(
        (element) => (element as ModelViewerElement).getCameraOrbit().radius,
      ),
    )
    .not.toBe(radius);
  await page.getByRole("button", { name: "复位", exact: true }).click();
  await expect
    .poll(async () =>
      viewer.evaluate(
        (element) => (element as ModelViewerElement).getCameraOrbit().theta,
      ),
    )
    .toBeCloseTo(Math.PI / 2, 3);
  const count = requests.length;
  await page.getByRole("button", { name: "放大查看模型" }).click();
  const dialog = page.getByRole("dialog", { name: MAP_MODEL_ASSETS[6]!.title });
  await expect(dialog.locator("model-viewer")).toHaveCount(1);
  await expect(page.locator("model-viewer")).toHaveCount(1);
  await dialog.getByRole("button", { name: "返回点位详情" }).click();
  await expect(dialog).toBeHidden();
  await expect(viewer).toBeVisible();
  expect(requests).toHaveLength(count);
  await page.getByRole("tab", { name: "概览", exact: true }).click();
  await expect(page.locator("model-viewer")).toHaveCount(0);
  await expect(page.getByText("近似定位", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "关闭点位详情" }).click();
  await expect(page.getByRole("region", { name: "点位详情" })).toHaveCount(0);
});

test("a failed GLB can be retried and a point without a model keeps its overview", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  const pattern = "**/models/mudu-gate/**";
  await page.route(pattern, (route) =>
    route.fulfill({ status: 404, body: "missing" }),
  );
  await page.goto("/workspace/map");
  // Focus lifts this real coordinate above nearby hit targets; a normal click
  // also waits for the initial map fit to settle instead of clicking mid-move.
  const marker = page.getByRole("button", {
    name: "地图点位 木渎古镇，可预览三维模型",
    exact: true,
  });
  await marker.focus();
  await marker.click();
  await expect(page.getByRole("button", { name: "重试加载模型" })).toBeVisible({
    timeout: 30_000,
  });
  await page.unroute(pattern);
  await page.getByRole("button", { name: "重试加载模型" }).click();
  await ready(page, 0);
  await page
    .getByRole("button", { name: "地图点位 严家花园", exact: true })
    .focus();
  await page
    .getByRole("button", { name: "地图点位 严家花园", exact: true })
    .press("Enter");
  await expect(
    page.getByRole("tab", { name: "模型", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("tab", { name: "概览", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.locator("model-viewer")).toHaveCount(0);
});

test("mobile and desktop layouts only mount the active model viewer", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await page.goto("/workspace/map");
  await selectModel(page, 0);
  await ready(page, 0);
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "放大查看模型" }).click();
  await expect(page.locator("model-viewer")).toHaveCount(1);
  await page.getByRole("button", { name: "返回点位详情" }).click();
  await expect(page.locator("model-viewer")).toHaveCount(1);
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(page.locator("model-viewer")).toHaveCount(0);
  await selectModel(page, 0);
  await ready(page, 0);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await ready(page, 0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("model-viewer")).toHaveCount(0);
});

test("a late previous model cannot overwrite the selected model", async ({
  page,
}) => {
  test.setTimeout(180_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  let release: (() => void) | undefined;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/models/mudu-gate/**", async (route) => {
    await held;
    await route.continue();
  });
  await page.goto("/workspace/map");
  await selectModel(page, 0);
  await expect(page.locator("model-viewer")).toHaveCount(1, {
    timeout: 30_000,
  });
  await selectModel(page, 1);
  release?.();
  await ready(page, 1);
  await expect(
    page.getByRole("heading", { name: MAP_MODEL_ASSETS[1]!.title }),
  ).toBeVisible();
  await expect(
    page.locator('[data-model-id="model-mudu-gate-v1"]'),
  ).toHaveCount(0);
});

test("model reference markers stay the same size while zooming an unpublished map", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await setup(page);
  await page.route("**/api/map/catalog", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        updated_at: "unpublished",
        data_notice: "未发布知识版本",
        points: [],
        layers: [],
        events: [],
        relations: [],
        trajectories: [],
        routes: [],
      }),
    }),
  );
  let modelRequests = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith(".glb")) modelRequests += 1;
  });
  await page.goto("/workspace/map");
  const markers = page.locator('[data-has-model="true"]');
  const badges = page.locator('[data-model-badge="true"]');
  await expect(markers).toHaveCount(7);
  await expect(page.locator('[data-has-model="false"]')).toHaveCount(0);
  const canvas = page.getByLabel("古舆地图画布");
  const dimensions = () =>
    badges.evaluateAll((elements) =>
      elements.map((element) => {
        const rect = element.getBoundingClientRect();
        const target = element.parentElement!.getBoundingClientRect();
        return {
          width: rect.width,
          height: rect.height,
          targetWidth: target.width,
          targetHeight: target.height,
        };
      }),
    );
  const expected = Array.from({ length: 7 }, () => ({
    width: 28,
    height: 28,
    targetWidth: 44,
    targetHeight: 44,
  }));
  await expect.poll(dimensions).toEqual(expected);
  for (const name of [
    "Zoom out",
    "Zoom out",
    "Zoom in",
    "Zoom in",
    "Zoom in",
  ]) {
    const before = Number(await canvas.getAttribute("data-map-camera-zoom"));
    await page.getByRole("button", { name, exact: true }).click();
    await expect
      .poll(async () =>
        Number(await canvas.getAttribute("data-map-camera-zoom")),
      )
      .toBeCloseTo(before + (name === "Zoom in" ? 1 : -1), 1);
    await expect.poll(dimensions).toEqual(expected);
  }
  expect(modelRequests).toBe(0);
  await page.route("**/models/mudu-gate/**", (route) =>
    route.fulfill({ status: 404, body: "test marker only" }),
  );
  await selectModel(page, 0);
  await expect.poll(dimensions).toEqual(expected);
  await expect(
    page.getByRole("tab", { name: "模型", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "概览", exact: true }).click();
  await page.getByRole("button", { name: "关闭点位详情" }).click();
  await page.screenshot({
    path: testInfo.outputPath("fixed-size-model-markers.png"),
  });
});
