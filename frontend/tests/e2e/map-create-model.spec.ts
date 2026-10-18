import { existsSync, statSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { type RegisteredMapModel } from "../../src/core/map/registered-models";

import { mockLangGraphAPI } from "./utils/mock-api";
import { refreshMockUser } from "./utils/refresh-mock-user";

const point = {
  id: "pt-model-create",
  entity_id: "entity-model-create",
  name: "模型接入测试古桥",
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
  summary: "交互测试输入",
  address: "木渎",
  evidence: [],
  start_year: null,
  end_year: null,
  record_kind: "reference",
};
const id = "71ca3eba-2a96-4140-a558-ea8130863cc5";
const proof = resolve("../reports/integration/2026-10-17/create-map-model");
const ply = process.env.COLORED_TEST_PLY;
const glb = resolve("public/models/mudu-gate/v1/model.3966d61b08b7.glb");
function asset(format: "ply" | "glb" = "ply"): RegisteredMapModel {
  return {
    id,
    point_id: point.id,
    entity_id: point.entity_id,
    title: "古桥接入模型",
    kind: format === "glb" ? "mesh" : "point_cloud",
    format,
    size_bytes: format === "glb" ? statSync(glb).size : statSync(ply!).size,
    sha256: "existing-fixture",
    source: "upload",
    created_at: "2026-10-17T00:00:00Z",
    preview_url: `/api/map/model-assets/${id}/file`,
    download_url: `/api/map/model-assets/${id}/file?download=true`,
  };
}
async function setup(
  page: Page,
  models: () => RegisteredMapModel[] = () => [],
) {
  mockLangGraphAPI(page);
  await page.route("**/api/map/catalog", (route) =>
    route.fulfill({
      json: {
        updated_at: "2026-10-17",
        data_notice: "软件测试",
        points: [point],
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
  await page.route("**/api/map/model-assets", (route) =>
    route.fulfill({ json: models() }),
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
    route.fulfill({ json: [] }),
  );
}
async function selectPoint(page: Page) {
  const marker = page.getByRole("button", {
    name: new RegExp(`地图点位 ${point.name}`),
  });
  await marker.focus();
  await marker.press("Enter");
}
async function importForm(page: Page, filename = ply!) {
  await page.getByRole("button", { name: "接入已有模型", exact: true }).click();
  await page.getByLabel("模型名称", { exact: true }).fill("古桥接入模型");
  await page.getByLabel("PLY 或 GLB 模型文件").setInputFiles(filename);
}

test("top-level create imports real colored PLY, persists across reload and adds a 3D marker", async ({
  page,
}) => {
  test.skip(!ply || !existsSync(ply), "Provide COLORED_TEST_PLY");
  test.setTimeout(90000);
  let models: RegisteredMapModel[] = [],
    posted = "",
    csrf = "";
  await setup(page, () => models);
  await page
    .context()
    .addCookies([
      { name: "csrf_token", value: "model-csrf", url: "http://127.0.0.1:3106" },
    ]);
  await page.route("**/api/map/model-assets", async (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: models });
    posted = route.request().postDataBuffer()!.toString();
    csrf = route.request().headers()["x-csrf-token"] ?? "";
    models = [asset()];
    return route.fulfill({ status: 201, json: models[0] });
  });
  await page.route(`**/api/map/model-assets/${id}/file`, (route) =>
    route.fulfill({ path: ply!, contentType: "application/octet-stream" }),
  );
  await page.goto("/workspace/map");
  await page.getByRole("button", { name: "创建模型", exact: true }).click();
  await expect(page.getByText("选择点位后即可创建模型。")).toBeVisible();
  await page.getByLabel("关联地图点位").selectOption(point.id);
  await importForm(page);
  await page
    .locator('[data-slot="dialog-content"]')
    .screenshot({ path: resolve(proof, "create-import-dialog.png") });
  await page
    .getByRole("button", { name: "保存并接入地图", exact: true })
    .click();
  await expect(page.locator('[data-slot="dialog-content"]')).toHaveCount(0);
  await expect(page.getByText(/个彩色点 · 拖动旋转/)).toBeVisible({
    timeout: 60000,
  });
  expect(posted).toContain(point.id);
  expect(posted).toContain('name="request_id"');
  expect(csrf).toBe("model-csrf");
  await expect(page.getByLabel("已接入模型")).toHaveValue(id);
  await expect(
    page.getByRole("button", { name: new RegExp(`地图点位 ${point.name}`) }),
  ).toHaveAttribute("data-has-model", "true");
  await page
    .getByLabel("彩色点云三维场景")
    .screenshot({ path: resolve(proof, "registered-rgb.png") });
  await page.reload();
  await selectPoint(page);
  await page.getByRole("tab", { name: "三维预览", exact: true }).click();
  await expect(page.getByLabel("已接入模型")).toHaveValue(id);
  await expect(page.getByText(/个彩色点 · 拖动旋转/)).toBeVisible({
    timeout: 60000,
  });
});

test("point detail creates an image reconstruction and completed output enters the public model tab", async ({
  page,
}) => {
  test.skip(!ply || !existsSync(ply), "Provide COLORED_TEST_PLY");
  test.setTimeout(90000);
  let created = false,
    done = false,
    submitted = "";
  const job = {
    id,
    title: `${point.name}影像重建`,
    point_id: point.id,
    point_name: point.name,
    input_type: "images",
    quality: "fast",
    status: "running",
    stage: "training",
    created_at: "2026-10-17T00:00:00Z",
    files: [
      { name: "a.jpg", size: 3 },
      { name: "b.jpg", size: 3 },
    ],
    log: "fixture",
  };
  await setup(page, () =>
    done ? [{ ...asset(), source: "reconstruction" }] : [],
  );
  await page.route("**/api/reconstructions?**", (route) =>
    route.fulfill({
      json: created ? [{ ...job, status: done ? "completed" : "running" }] : [],
    }),
  );
  await page.route("**/api/reconstructions", (route) => {
    submitted = route.request().postDataBuffer()!.toString();
    created = true;
    return route.fulfill({ status: 202, json: job });
  });
  await page.route(`**/api/reconstructions/${id}`, (route) => {
    done = true;
    return route.fulfill({
      json: {
        ...job,
        status: "completed",
        stage: "completed",
        artifact: {
          kind: "point_cloud",
          point_count: 155770,
          size: statSync(ply!).size,
          sha256: "fixture",
        },
      },
    });
  });
  await page.route(`**/api/map/model-assets/${id}/file`, (route) =>
    route.fulfill({ path: ply!, contentType: "application/octet-stream" }),
  );
  await page.goto("/workspace/map");
  await selectPoint(page);
  await page
    .getByRole("button", { name: `为${point.name}创建模型`, exact: true })
    .click();
  await expect(page.getByLabel("关联地图点位")).toHaveValue(point.id);
  await page.getByLabel("视频或多张照片").setInputFiles([
    { name: "a.jpg", mimeType: "image/jpeg", buffer: Buffer.from("aaa") },
    { name: "b.jpg", mimeType: "image/jpeg", buffer: Buffer.from("bbb") },
  ]);
  await page.getByRole("button", { name: "上传并重建", exact: true }).click();
  await expect(page.locator('[data-slot="dialog-content"]')).toHaveCount(0);
  expect(submitted).toContain(point.id);
  await expect(page.getByText("重建完成", { exact: true })).toBeVisible({
    timeout: 20000,
  });
  await page.getByRole("tab", { name: "三维预览", exact: true }).click();
  await expect(page.getByLabel("已接入模型")).toHaveValue(id);
  await expect(page.getByText(/个彩色点 · 拖动旋转/)).toBeVisible({
    timeout: 60000,
  });
});

test("mobile import shows useful errors and retries the same idempotency request", async ({
  page,
}) => {
  test.skip(!ply || !existsSync(ply), "Provide COLORED_TEST_PLY");
  test.setTimeout(90000);
  await page.setViewportSize({ width: 390, height: 844 });
  let models: RegisteredMapModel[] = [],
    attempts = 0;
  const keys: string[] = [];
  await setup(page, () => models);
  await page.route("**/api/map/model-assets", (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: models });
    const body = route.request().postDataBuffer()!.toString();
    keys.push(
      /name="request_id"\r\n\r\n([^\r\n]+)/.exec(body)?.[1] ?? "missing",
    );
    if (++attempts === 1)
      return route.fulfill({
        status: 503,
        json: { detail: "存储暂不可用，请重试" },
      });
    models = [asset()];
    return route.fulfill({ status: 201, json: models[0] });
  });
  await page.route(`**/api/map/model-assets/${id}/file`, (route) =>
    route.fulfill({ path: ply!, contentType: "application/octet-stream" }),
  );
  await page.goto("/workspace/map");
  await selectPoint(page);
  await page
    .getByRole("button", { name: `为${point.name}创建模型`, exact: true })
    .click();
  await importForm(page);
  await page
    .getByRole("button", { name: "保存并接入地图", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText("存储暂不可用");
  await expect(page.locator("body")).toHaveJSProperty("scrollWidth", 390);
  await page
    .locator('[data-slot="dialog-content"]')
    .screenshot({ path: resolve(proof, "create-mobile-error.png") });
  await page
    .getByRole("button", { name: "保存并接入地图", exact: true })
    .click();
  await expect(page.locator('[data-slot="dialog-content"]')).toHaveCount(0);
  expect(keys).toHaveLength(2);
  expect(keys[0]).not.toBe("missing");
  expect(keys[0]).toBe(keys[1]);
  await expect(page.getByText(/个彩色点 · 拖动旋转/)).toBeVisible({
    timeout: 60000,
  });
});

test("imported GLB renders through the existing viewer and ordinary readers can preview without write controls", async ({
  page,
}) => {
  test.skip(!existsSync(glb), "Existing GLB required");
  test.setTimeout(120000);
  let models: RegisteredMapModel[] = [];
  await setup(page, () => models);
  await page.route("**/api/map/model-assets", (route) => {
    if (route.request().method() === "POST") {
      models = [asset("glb")];
      return route.fulfill({ status: 201, json: models[0] });
    }
    return route.fulfill({ json: models });
  });
  await page.route(`**/api/map/model-assets/${id}/file`, (route) =>
    route.fulfill({ path: glb, contentType: "model/gltf-binary" }),
  );
  await page.goto("/workspace/map");
  await selectPoint(page);
  await page
    .getByRole("button", { name: `为${point.name}创建模型`, exact: true })
    .click();
  await importForm(page, glb);
  await page
    .getByRole("button", { name: "保存并接入地图", exact: true })
    .click();
  await expect(page.locator('[data-model-id="' + id + '"]')).toHaveAttribute(
    "data-model-state",
    "ready",
    { timeout: 60000 },
  );
  await expect(page.locator("model-viewer")).toHaveCount(1);
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      json: {
        id: "reader",
        email: "reader@test.local",
        system_role: "user",
        needs_setup: false,
      },
    }),
  );
  await refreshMockUser(page);
  await expect(
    page.getByRole("button", { name: "创建模型", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: `为${point.name}创建模型`, exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("tab", { name: "影像重建", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator("model-viewer")).toHaveCount(1);
  await page.screenshot({
    path: resolve(proof, "registered-glb-reader.png"),
    fullPage: true,
  });
});
