import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";
import { refreshMockUser } from "./utils/refresh-mock-user";

const proof = resolve("../reports/integration/2026-10-17/create-map-point");
const basePoint = {
  id: "custom-point-test",
  entity_id: "custom-place-test",
  name: "新建研习点",
  entity_type: "place",
  lon: 120.506,
  lat: 31.253,
  confidence: "exact",
  geometry_type: "point",
  coordinate_system: "WGS84",
  basis: "管理员地图选点",
  dynasties: [],
  heritage_status: "uncertain",
  access_status: "verify_before_visit",
  summary: "自建点位",
  address: "地图选点",
  evidence: [],
  record_kind: "custom",
  release_id: null,
  review_status: null,
  start_year: null,
  end_year: null,
};

async function setup(page: Page, failFirst = false) {
  mockLangGraphAPI(page);
  const saved: (typeof basePoint)[] = [];
  const requests: Array<{
    name: string;
    lon: number;
    lat: number;
    request_id: string;
  }> = [];
  await page.route("**/api/map/catalog", (route) =>
    route.fulfill({
      json: {
        updated_at: "unpublished",
        data_notice: "软件测试",
        points: [],
        layers: [],
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
  await page.route("**/api/map/custom-points", async (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: saved });
    const body = route.request().postDataJSON() as (typeof requests)[number];
    requests.push(body);
    expect(route.request().headers()["x-csrf-token"]).toBe("point-test-csrf");
    if (failFirst && requests.length === 1)
      return route.fulfill({
        status: 503,
        json: { detail: "点位暂时保存失败，请重试" },
      });
    saved.push({ ...basePoint, name: body.name, lon: body.lon, lat: body.lat });
    return route.fulfill({ status: 201, json: saved.at(-1) });
  });
  await page.route("**/api/reconstructions/capabilities", (route) =>
    route.fulfill({
      json: {
        enabled: true,
        max_bytes: 2147483648,
        max_files: 500,
        extensions: [".jpg", ".mp4"],
      },
    }),
  );
  await page.route("**/api/reconstructions?**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/operations/events", (route) =>
    route.fulfill({ status: 204 }),
  );
  await page.route("https://tile.openstreetmap.de/**", (route) =>
    route.fulfill({
      contentType: "image/png",
      body: Buffer.from(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nWQAAAAASUVORK5CYII=",
        "base64",
      ),
    }),
  );
  await page.context().addCookies([
    {
      name: "csrf_token",
      value: "point-test-csrf",
      url: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3106",
    },
  ]);
  return { saved, requests };
}

async function pick(page: Page) {
  const map = page.locator('[data-map-engine="maplibre-gl"]');
  await expect(map).toHaveAttribute("data-map-picking", "true");
  const canvas = map.locator("canvas");
  await expect(canvas).toBeVisible();
  await canvas.click({ position: { x: 100, y: 270 } });
  await expect(
    page.getByRole("dialog", { name: "创建点位", exact: true }),
  ).toBeVisible();
  await expect(page.locator("[data-draft-point]")).toHaveCount(1);
}

test("map click creates a named persistent location and restores it after reload", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const { saved, requests } = await setup(page);
  await page.goto("/workspace/map");
  await refreshMockUser(page);
  await page.getByRole("button", { name: "创建点位", exact: true }).click();
  await expect(
    page.getByText("请点击地图选择新点位，可拖动或缩放地图。"),
  ).toBeVisible();
  await pick(page);
  await expect(page.getByRole("button", { name: "保存点位" })).toBeDisabled();
  await page.getByLabel("点位名称").fill(" 新建研习点 ");
  mkdirSync(proof, { recursive: true });
  await page.screenshot({ path: resolve(proof, "pick-name-desktop.png") });
  await page.getByRole("button", { name: "保存点位" }).click();
  await expect(
    page.getByRole("dialog", { name: "创建点位", exact: true }),
  ).toHaveCount(0);
  expect(requests).toHaveLength(1);
  expect(requests[0]!.name).toBe("新建研习点");
  expect(
    Number.isFinite(requests[0]!.lon) && Number.isFinite(requests[0]!.lat),
  ).toBe(true);
  expect(saved).toHaveLength(1);
  await expect(
    page.getByRole("button", { name: /地图点位 新建研习点/ }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: /地图点位 新建研习点/ }),
  ).toBeVisible();
});

test("model dialog can create a location then selects it for model import", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  await page.goto("/workspace/map");
  await refreshMockUser(page);
  await page.getByRole("button", { name: "创建模型", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "创建点位", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "创建点位", exact: true }),
  ).toHaveCount(0);
  await pick(page);
  await page.getByLabel("点位名称").fill("新建研习点");
  await page.getByRole("button", { name: "保存点位" }).click();
  await expect(
    page.getByRole("dialog", { name: "创建模型", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("关联地图点位")).toHaveValue(basePoint.id);
  await expect(
    page.getByLabel("关联地图点位").locator("option:checked"),
  ).toHaveText("新建研习点");
});

test("mobile can reselect cancel and retry without duplicate requests or overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { requests, saved } = await setup(page, true);
  await page.goto("/workspace/map");
  await refreshMockUser(page);
  await page.getByRole("button", { name: "创建点位", exact: true }).click();
  await page.getByRole("button", { name: "取消选点" }).click();
  expect(requests).toHaveLength(0);
  await page.getByRole("button", { name: "创建点位", exact: true }).click();
  await pick(page);
  await page.getByRole("button", { name: "重新选点" }).click();
  await expect(page.locator("[data-draft-point]")).toHaveCount(0);
  await pick(page);
  await page.getByLabel("点位名称").fill("移动端选点");
  await page.getByRole("button", { name: "保存点位" }).click();
  await expect(page.getByRole("alert")).toContainText("请重试");
  await expect(page.getByLabel("点位名称")).toHaveValue("移动端选点");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  mkdirSync(proof, { recursive: true });
  await page.screenshot({
    path: resolve(proof, "pick-mobile-error.png"),
    animations: "disabled",
  });
  await page.getByRole("button", { name: "保存点位" }).click();
  await expect(
    page.getByRole("dialog", { name: "创建点位", exact: true }),
  ).toHaveCount(0);
  expect(requests).toHaveLength(2);
  expect(requests[0]!.request_id).toBe(requests[1]!.request_id);
  expect(saved).toHaveLength(1);
});

test("readers can view saved locations without point creation controls", async ({
  page,
}) => {
  await setup(page);
  await page.route("**/api/map/custom-points", (route) =>
    route.fulfill({ json: [basePoint] }),
  );
  await page.goto("/workspace/map");
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
    page.getByRole("button", { name: /地图点位 新建研习点/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "创建点位", exact: true }),
  ).toHaveCount(0);
});

test("a new point can rebuild the same photos after failure with a fresh request and retained history", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await setup(page);
  const ids = [
    "71ca3eba-2a96-4140-a558-ea8130863cc5",
    "71ca3eba-2a96-4140-a558-ea8130863cc6",
  ];
  const jobs: Array<Record<string, unknown>> = [];
  const requestKeys: string[] = [];
  await page.route("**/api/reconstructions?**", (route) =>
    route.fulfill({ json: jobs }),
  );
  await page.route("**/api/reconstructions", (route) => {
    const body = route.request().postDataBuffer()!.toString();
    expect(body).toContain(basePoint.id);
    expect(route.request().headers()["x-csrf-token"]).toBe("point-test-csrf");
    const key = /name="request_id"\r\n\r\n([^\r]+)/.exec(body)?.[1];
    expect(key).toBeTruthy();
    requestKeys.push(key!);
    const job = {
      id: ids[jobs.length],
      title: jobs.length ? "重新建立模型" : "首次建立模型",
      point_id: basePoint.id,
      point_name: "重建研习点",
      input_type: "images",
      quality: "fast",
      status: "running",
      stage: "training",
      created_at: "2026-10-17T12:00:00Z",
      files: [
        { name: "a.jpg", size: 3 },
        { name: "b.jpg", size: 3 },
      ],
      log: "software fixture",
    };
    jobs.unshift(job);
    return route.fulfill({ status: 202, json: job });
  });
  for (let index = 0; index < ids.length; index++) {
    await page.route(`**/api/reconstructions/${ids[index]}`, (route) => {
      const job = jobs.find((item) => item.id === ids[index])!;
      if (index === 0)
        Object.assign(job, {
          status: "failed",
          stage: "failed",
          error: "首次重建失败，可重新上传",
        });
      else
        Object.assign(job, {
          status: "completed",
          stage: "completed",
          artifact: {
            kind: "point_cloud",
            point_count: 1,
            size: 160,
            sha256: "software-fixture",
          },
        });
      return route.fulfill({ json: job });
    });
  }
  await page.goto("/workspace/map");
  await refreshMockUser(page);
  await page.getByRole("button", { name: "创建模型", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "创建点位", exact: true })
    .click();
  await pick(page);
  await page.getByLabel("点位名称").fill("重建研习点");
  await page.getByRole("button", { name: "保存点位" }).click();
  const photos = [
    { name: "a.jpg", mimeType: "image/jpeg", buffer: Buffer.from("aaa") },
    { name: "b.jpg", mimeType: "image/jpeg", buffer: Buffer.from("bbb") },
  ];
  for (let attempt = 0; attempt < 2; attempt++) {
    await page
      .getByLabel("重建名称", { exact: true })
      .fill(attempt ? "重新建立模型" : "首次建立模型");
    await page.getByLabel("视频或多张照片").setInputFiles(photos);
    await page.getByRole("button", { name: "上传并重建", exact: true }).click();
    await expect(
      page.getByText(attempt ? "重建完成" : "重建失败", { exact: true }),
    ).toBeVisible({ timeout: 20000 });
  }
  expect(requestKeys).toHaveLength(2);
  expect(requestKeys[0]).not.toBe(requestKeys[1]);
  expect(jobs.map((item) => item.id)).toEqual([...ids].reverse());
  await expect(
    page.getByRole("heading", { name: "首次建立模型", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "重新建立模型", exact: true }),
  ).toBeVisible();
  await page.reload();
  const marker = page.getByRole("button", { name: /地图点位 重建研习点/ });
  await marker.focus();
  await marker.press("Enter");
  await page.getByRole("tab", { name: "影像重建", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "首次建立模型", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "重新建立模型", exact: true }),
  ).toBeVisible();
});
