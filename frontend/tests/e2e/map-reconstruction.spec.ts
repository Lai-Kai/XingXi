import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const point = {
  id: "pt-reconstruction",
  entity_id: "entity-reconstruction",
  name: "重建测试古桥",
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
  summary: "软件交互夹具",
  address: "木渎",
  evidence: [],
  start_year: null,
  end_year: null,
  record_kind: "reference",
};
const job = {
  id: "71ca3eba-2a96-4140-a558-ea8130863cc5",
  title: "古桥环拍重建",
  point_id: point.id,
  point_name: point.name,
  input_type: "images",
  quality: "fast",
  status: "running",
  stage: "training",
  created_at: "2026-10-16T10:00:00Z",
  files: [
    { name: "a.jpg", size: 20 },
    { name: "b.jpg", size: 20 },
  ],
  log: "COLMAP 完成，正在训练",
};
async function setup(
  page: Page,
  existing: unknown[] = [],
  selectedPoint = point,
) {
  mockLangGraphAPI(page);
  await page.route("**/api/map/catalog", (route) =>
    route.fulfill({
      json: {
        updated_at: "2026-10-16",
        data_notice: "软件测试",
        points: [selectedPoint],
        layers: [
          {
            id: "osm-current",
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
  await page.route("**/api/operations/events", (route) =>
    route.fulfill({ status: 204 }),
  );
  await page.route("**/api/reconstructions/capabilities", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        max_bytes: 2147483648,
        max_files: 500,
        extensions: [".jpg", ".png", ".mp4"],
      },
    }),
  );
  await page.route("**/api/reconstructions?**", (route) =>
    route.fulfill({ json: existing }),
  );
  await page.route(`**/api/reconstructions/${job.id}`, (route) =>
    route.fulfill({ json: job }),
  );
  await page.route(`**/api/reconstructions/${job.id}/cancel`, (route) =>
    route.fulfill({
      json: { ...job, status: "cancelled", stage: "cancelled" },
    }),
  );
}
async function open(page: Page) {
  await page.goto("/workspace/map");
  const marker = page.getByRole("button", { name: /地图点位 重建测试古桥/ });
  await marker.focus();
  await marker.press("Enter");
  await page.getByRole("tab", { name: "影像重建", exact: true }).click();
  await expect(page.getByLabel("视频或多张照片")).toBeEnabled();
}

test("optional image preparation sends its settings and restores progress", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/api/reconstructions/capabilities", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        flux3_enabled: true,
        max_bytes: 2147483648,
        max_files: 500,
        extensions: [".png"],
      },
    }),
  );
  let posted = "";
  const processing = {
    ...job,
    preprocessing: "flux3",
    pipeline_profile: "flux3_rgb_subject_v1",
    stage: "preprocessing",
    preprocess_progress: { completed: 3, total: 16 },
  };
  await page.route("**/api/reconstructions", async (route) => {
    posted = route.request().postDataBuffer()!.toString();
    await route.fulfill({ status: 202, json: processing });
  });
  await page.route(`**/api/reconstructions/${job.id}`, (route) =>
    route.fulfill({ json: processing }),
  );
  await open(page);
  await expect(page.getByLabel("图片预处理", { exact: true })).toHaveValue(
    "none",
  );
  await page.getByLabel("图片预处理", { exact: true }).selectOption("flux3");
  await page
    .getByLabel("图片处理要求", { exact: true })
    .fill("Keep the bridge and replace the background with white.");
  await page.getByLabel("视频或多张照片").setInputFiles([
    { name: "a.png", mimeType: "image/png", buffer: Buffer.from("photo-a") },
    { name: "b.png", mimeType: "image/png", buffer: Buffer.from("photo-b") },
  ]);
  await page.getByRole("button", { name: "上传并重建" }).click();
  await expect(
    page.getByText("已启用图片预处理 · 3/16", { exact: true }),
  ).toBeVisible();
  expect(posted).toContain('name="preprocessing"');
  expect(posted).toContain("flux3");
  expect(posted).toContain(
    "Keep the bridge and replace the background with white.",
  );
  await expect(
    page.getByRole("region", { name: "影像重建", exact: true }),
  ).not.toContainText(/FLUX|OOOSplat|ComfyUI|Gateway/i);
  if (process.env.TEST_REPORT_DIR)
    await page
      .getByRole("region", { name: "影像重建", exact: true })
      .screenshot({
        path: resolve(
          process.env.TEST_REPORT_DIR,
          "functional-reconstruction.png",
        ),
      });
});

test("worker names and raw diagnostics stay out of visible reconstruction states", async ({
  page,
}) => {
  const current = {
    ...job,
    preprocessing: "flux3",
    stage: "PrivateVendorModel-v7",
    log: "OOOSplat / ComfyUI /data/PrivateProject/worker.py",
    error: "PrivateVendorModel-v7 @ /data/PrivateProject/worker.py",
  };
  await setup(page, [current]);
  await page.route(`**/api/reconstructions/${job.id}`, (route) =>
    route.fulfill({ json: current }),
  );
  await open(page);
  const panel = page.getByRole("region", { name: "影像重建", exact: true });
  await expect(panel.getByText("正在处理", { exact: true })).toBeVisible();
  await expect(panel.getByRole("alert")).toHaveText("处理未完成，请稍后重试。");
  await expect(panel).not.toContainText(
    /FLUX|OOOSplat|ComfyUI|Gateway|PrivateVendorModel|PrivateProject|\/data\//i,
  );
  await expect(panel.getByText("运行日志", { exact: true })).toHaveCount(0);
});

test("model provenance keeps its category and license without naming the generator", async ({
  page,
}) => {
  await setup(page, [], {
    ...point,
    id: "pt-yongan-bridge",
    entity_id: "entity-bridge-yongan",
  });
  await page.route("**/models/**/*.glb", (route) =>
    route.fulfill({ status: 404 }),
  );
  await open(page);
  await page.getByRole("tab", { name: /3D 建筑研习/ }).click();
  const preview = page.getByRole("region", {
    name: "三维模型预览",
    exact: true,
  });
  await preview.getByText("模型来源与许可", { exact: true }).click();
  await expect(
    preview.getByText("来源：生成示意", { exact: true }),
  ).toBeVisible();
  await expect(
    preview.getByText("许可：待确认", { exact: true }),
  ).toBeVisible();
  await expect(preview).not.toContainText(/Tripo|PrivateVendorModel/i);
});

test("uploads photos with point binding and CSRF then cancels only the returned task", async ({
  page,
}) => {
  await setup(page);
  await page.context().addCookies([
    {
      name: "csrf_token",
      value: "reconstruction-csrf",
      url: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    },
  ]);
  let posted = "",
    csrf: string | undefined;
  await page.route("**/api/reconstructions", async (route) => {
    posted = route.request().postDataBuffer()!.toString();
    csrf = route.request().headers()["x-csrf-token"];
    await route.fulfill({ status: 202, json: job });
  });
  await open(page);
  await page.getByLabel("重建名称", { exact: true }).fill(job.title);
  await page.getByLabel("视频或多张照片").setInputFiles([
    { name: "a.jpg", mimeType: "image/jpeg", buffer: Buffer.from("photo-a") },
    { name: "b.jpg", mimeType: "image/jpeg", buffer: Buffer.from("photo-b") },
  ]);
  await page.getByRole("button", { name: "上传并重建" }).click();
  await expect(
    page.getByRole("heading", { name: job.title, exact: true }),
  ).toBeVisible();
  expect(posted).toContain(point.id);
  expect(posted).toContain('name="request_id"');
  expect(csrf).toBe("reconstruction-csrf");
  await page.getByRole("button", { name: "取消重建" }).click();
  await expect(page.getByText("已取消", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "取消重建" })).toHaveCount(0);
  await page.screenshot({
    path: resolve(
      "../reports/integration/2026-10-16/ooosplat/reconstruction-desktop.png",
    ),
    fullPage: true,
  });
});

test("restores a running video job after reload and rejects mixed upload before sending", async ({
  page,
}) => {
  await setup(page, [{ ...job, input_type: "video" }]);
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  await expect(
    page.getByRole("heading", { name: job.title, exact: true }),
  ).toBeVisible();
  await page.getByLabel("视频或多张照片").setInputFiles([
    { name: "a.jpg", mimeType: "image/jpeg", buffer: Buffer.from("photo-a") },
    {
      name: "ring.mp4",
      mimeType: "video/mp4",
      buffer: Buffer.from("0000ftypmp42"),
    },
  ]);
  await page.getByRole("button", { name: "上传并重建" }).click();
  await expect(page.getByRole("alert")).toContainText("不能混合上传");
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);
  await page.screenshot({
    path: resolve(
      "../reports/integration/2026-10-16/ooosplat/reconstruction-mobile.png",
    ),
    fullPage: true,
  });
});

test("native Gaussian preview keeps its own artifact even when a point cloud is available", async ({
  page,
}) => {
  const nativeUrl = `/api/reconstructions/${job.id}/artifact/final.ply`;
  const rgbUrl = `/api/reconstructions/${job.id}/artifact/rgb_points.ply`;
  await setup(page, [
    {
      ...job,
      status: "completed",
      stage: "completed",
      artifact: { kind: "gaussian", size: 1024, splat_count: 500000 },
      rgb_artifact_url: rgbUrl,
    },
  ]);
  let nativeRequests = 0;
  let rgbRequests = 0;
  await page.route(`**${nativeUrl}`, (route) => {
    nativeRequests++;
    return route.fulfill({ status: 503, body: "temporarily unavailable" });
  });
  await page.route(`**${rgbUrl}`, (route) => {
    rgbRequests++;
    return route.fulfill({ status: 503, body: "temporarily unavailable" });
  });
  await open(page);
  const panel = page.getByRole("region", { name: "影像重建", exact: true });
  await expect(
    panel.getByRole("link", { name: "下载高斯 PLY", exact: true }),
  ).toHaveAttribute("href", nativeUrl);
  await expect(
    panel.getByRole("link", { name: "下载普通点云", exact: true }),
  ).toHaveAttribute("href", rgbUrl);
  await panel.getByRole("button", { name: "预览高斯点", exact: true }).click();
  await expect(panel.getByRole("alert")).toBeVisible();
  expect(nativeRequests).toBe(1);
  expect(rgbRequests).toBe(0);
  await panel
    .getByRole("button", { name: "预览普通点云", exact: true })
    .click();
  await expect.poll(() => rgbRequests).toBe(1);
});

test("renders a previously completed real Gaussian PLY on demand and disposes on tab switch", async ({
  page,
}) => {
  test.setTimeout(90000);
  const ply = process.env.OOOSPLAT_TEST_PLY;
  test.skip(
    !ply || !existsSync(ply),
    "Set OOOSPLAT_TEST_PLY to a verified existing Gaussian result",
  );
  const completed = {
    ...job,
    status: "completed",
    stage: "completed",
    artifact: {
      size: 9177230,
      sha256: "fixture-existing-real-result",
      splat_count: 38880,
    },
  };
  await setup(page, [completed]);
  await page.route(
    `**/api/reconstructions/${job.id}/artifact/final.ply`,
    (route) =>
      route.fulfill({ path: ply!, contentType: "application/octet-stream" }),
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await open(page);
  await expect(page.getByLabel("高斯点三维场景")).toHaveCount(0);
  await page.getByRole("button", { name: "预览高斯点" }).click();
  await expect(page.getByText(/拖动旋转 · 滚轮缩放/)).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByLabel("高斯点三维场景")).toBeVisible();
  await page.getByLabel("高斯点三维场景").scrollIntoViewIfNeeded();
  await page.getByLabel("高斯点三维场景").screenshot({
    path: resolve(
      "../reports/integration/2026-10-16/ooosplat/gaussian-canvas.png",
    ),
  });
  await page.screenshot({
    path: resolve(
      "../reports/integration/2026-10-16/ooosplat/gaussian-preview.png",
    ),
    fullPage: true,
  });
  await page.getByRole("tab", { name: "史料考据", exact: true }).click();
  await expect(page.getByLabel("高斯点三维场景")).toHaveCount(0);
  expect(errors).toEqual([]);
});

const colorReports = "../reports/integration/2026-10-17/colored-ply";

test("opens a real local RGB PLY with its colors, supports one expanded canvas and releases on tab switch", async ({
  page,
}) => {
  test.setTimeout(90000);
  const ply = process.env.COLORED_TEST_PLY;
  test.skip(
    !ply || !existsSync(ply),
    "Set COLORED_TEST_PLY to an existing RGB/RGBA result",
  );
  await setup(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await open(page);
  await page.getByRole("tab", { name: "三维预览", exact: true }).click();
  await expect(page.locator("canvas[aria-label$='三维场景']")).toHaveCount(0);
  await page.getByLabel("打开本地 PLY").setInputFiles(ply!);
  await expect(page.getByText(/个彩色点.*拖动旋转/)).toBeVisible({
    timeout: 60000,
  });
  const canvas = page.getByLabel("彩色三维场景");
  await expect(canvas).toBeVisible();
  await expect(page.getByLabel("高斯点三维场景")).toHaveCount(0);
  await canvas.screenshot({
    path: resolve(colorReports, "local-rgb-canvas.png"),
  });
  await page.getByLabel("使用文件透明度").check();
  await expect(page.getByLabel("使用文件透明度")).toBeChecked();
  await page.getByLabel("使用文件透明度").uncheck();
  await page.getByLabel("点大小", { exact: true }).fill("3");
  await page.getByLabel("场景背景").selectOption("#f4f1e9");
  await page.getByRole("button", { name: "翻转上下", exact: true }).click();
  await page.getByRole("button", { name: "复位视角", exact: true }).click();
  const size = (await canvas.boundingBox())!;
  await page.getByRole("button", { name: "放大查看场景", exact: true }).click();
  await expect(page.locator('[data-slot="dialog-content"]')).toBeVisible();
  await expect(canvas).toHaveCount(1);
  await expect(
    page.getByRole("dialog").getByLabel("彩色三维场景"),
  ).toBeVisible();
  await expect
    .poll(async () => {
      const expanded = (await canvas.boundingBox())!;
      return expanded.width * expanded.height;
    })
    .toBeGreaterThan(size.width * size.height);
  await page
    .getByRole("dialog")
    .screenshot({ path: resolve(colorReports, "local-rgb-expanded.png") });
  await page.getByRole("button", { name: "返回点位详情", exact: true }).click();
  // Mobile retains its point-details Sheet after the expanded viewer closes.
  await expect(page.locator('[data-slot="dialog-content"]')).toHaveCount(0);
  await expect(canvas).toHaveCount(1);
  await expect(canvas).toBeVisible();
  await page.getByRole("tab", { name: "史料考据", exact: true }).click();
  await expect(canvas).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("previews a completed remote RGB artifact without assuming Gaussian metadata or downloading early", async ({
  page,
}) => {
  const ply = process.env.COLORED_TEST_PLY;
  test.skip(
    !ply || !existsSync(ply),
    "Set COLORED_TEST_PLY to an existing RGB/RGBA result",
  );
  test.setTimeout(90000);
  const completed = {
    ...job,
    status: "completed",
    stage: "completed",
    artifact: {
      kind: "point_cloud",
      point_count: 487474,
      size: 7799841,
      sha256: "existing-real-result",
    },
  };
  await setup(page, [completed]);
  let downloads = 0;
  await page.route(
    `**/api/reconstructions/${job.id}/artifact/final.ply`,
    (route) => {
      downloads++;
      return route.fulfill({
        path: ply!,
        contentType: "application/octet-stream",
      });
    },
  );
  await open(page);
  await expect(page.getByText(/487,474 个彩色点/)).toBeVisible();
  expect(downloads).toBe(0);
  await page.getByRole("button", { name: "预览普通点云", exact: true }).click();
  await expect(page.getByText(/个彩色点.*拖动旋转/)).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByLabel("彩色三维场景")).toBeVisible();
  expect(downloads).toBe(1);
  await expect(
    page.getByRole("link", { name: "下载普通点云", exact: true }),
  ).toHaveAttribute(
    "href",
    `/api/reconstructions/${job.id}/artifact/final.ply`,
  );
  await page
    .getByLabel("彩色三维场景")
    .screenshot({ path: resolve(colorReports, "remote-rgb-canvas.png") });
  await page.getByRole("button", { name: "关闭预览", exact: true }).click();
  await expect(page.getByLabel("彩色三维场景")).toHaveCount(0);
});

test("recovers from invalid PLY and supports colored point clouds in the mobile map sheet", async ({
  page,
}) => {
  const ply = process.env.COLORED_TEST_PLY;
  test.skip(
    !ply || !existsSync(ply),
    "Set COLORED_TEST_PLY to an existing RGB/RGBA result",
  );
  test.setTimeout(90000);
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  await open(page);
  await page.getByRole("tab", { name: "三维预览", exact: true }).click();
  await page.getByLabel("打开本地 PLY").setInputFiles({
    name: "invalid.ply",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("not a ply"),
  });
  await expect(page.getByRole("alert")).toContainText("模型文件无法读取");
  await page.getByLabel("打开本地 PLY").setInputFiles(ply!);
  await expect(page.getByText(/个彩色点.*拖动旋转/)).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByLabel("彩色三维场景")).toHaveCount(1);
  await page.getByRole("button", { name: "放大查看场景", exact: true }).click();
  await expect(page.locator('[data-slot="dialog-content"]')).toBeVisible();
  await expect(page.getByLabel("彩色三维场景")).toHaveCount(1);
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);
  await page
    .locator('[data-slot="dialog-content"]')
    .screenshot({ path: resolve(colorReports, "rgb-mobile-expanded.png") });
  await page.getByRole("button", { name: "返回点位详情", exact: true }).click();
  await expect(page.locator('[data-slot="dialog-content"]')).toHaveCount(0);
  await page.getByRole("button", { name: "关闭本地文件", exact: true }).click();
  await expect(page.getByLabel("彩色三维场景")).toHaveCount(0);
});

test("connection retry uses explicit POST for the same task", async ({
  page,
}) => {
  await setup(page, [
    { ...job, status: "transferring", connection_error: "远程连接暂不可用" },
  ]);
  let retries = 0;
  await page.route(
    `**/api/reconstructions/${job.id}/retry-connection`,
    async (route) => {
      expect(route.request().method()).toBe("POST");
      retries += 1;
      await route.fulfill({ json: job });
    },
  );
  await open(page);
  await page.getByRole("button", { name: "重试连接", exact: true }).click();
  await expect.poll(() => retries).toBe(1);
});

test("map refreshes registered results while no reconstruction panel is open", async ({
  page,
}) => {
  await page.clock.install();
  await setup(page);
  let reads = 0;
  await page.route("**/api/map/model-assets/page?**", async (route) => {
    reads += 1;
    await route.fulfill({ json: { data: [], next_cursor: null } });
  });
  await page.goto("/workspace/map");
  await expect.poll(() => reads).toBe(1);
  await page.clock.runFor(15_100);
  await expect.poll(() => reads).toBe(2);
  await expect(page.getByRole("heading", { name: job.title })).toHaveCount(0);
});

test("failed parallel job resumes explicitly and completed job offers RGB download", async ({
  page,
}) => {
  await setup(page, [
    {
      ...job,
      status: "failed",
      stage: "failed",
      resumable: true,
      error: "远端任务中断",
    },
  ]);
  let resumes = 0;
  await page.route(`**/api/reconstructions/${job.id}/resume`, async (route) => {
    expect(route.request().method()).toBe("POST");
    resumes += 1;
    await route.fulfill({
      json: {
        ...job,
        status: "completed",
        resumable: false,
        artifact: { kind: "gaussian", size: 2048, splat_count: 2 },
        rgb_artifact_url: `/api/reconstructions/${job.id}/artifact/rgb_points.ply`,
      },
    });
  });
  await open(page);
  await page.getByRole("button", { name: "继续处理", exact: true }).click();
  await expect.poll(() => resumes).toBe(1);
  await expect(
    page.getByRole("button", { name: "继续处理", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "下载普通点云", exact: true }),
  ).toHaveAttribute(
    "href",
    `/api/reconstructions/${job.id}/artifact/rgb_points.ply`,
  );
});

test("worker filesystem permissions do not appear as account authorization failures", async ({
  page,
}) => {
  await setup(page, [
    {
      ...job,
      status: "failed",
      stage: "failed",
      error:
        "[Errno 13] Permission denied: '/data/private/gpu_locks/allocator.lock'",
    },
  ]);
  await open(page);
  await expect(
    page
      .getByRole("region", { name: "影像重建", exact: true })
      .getByRole("alert"),
  ).toContainText("服务端权限");
  await expect(
    page.getByText("当前账号无权执行此操作，请联系管理员。", { exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByText("/data/private/gpu_locks/allocator.lock", { exact: false }),
  ).toHaveCount(0);
});
