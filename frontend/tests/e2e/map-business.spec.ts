import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const appOrigin = new URL(
  process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
).origin;

const evidence = {
  id: "osm-way-1",
  title: "严家花园 OpenStreetMap 要素",
  publisher: "OpenStreetMap contributors",
  url: "https://www.openstreetmap.org/way/1332751496",
  kind: "current_map",
  retrieved_at: "2026-07-29",
  note: "用于当前地物定位。",
  quote: "公开条目记载永安桥始建。",
};

const catalog = {
  updated_at: "2026-07-29",
  data_notice: "公开资料在正式发布前仍需人工复核。",
  points: [
    {
      id: "pt-yan-garden",
      entity_id: "entity-garden-yan",
      name: "严家花园",
      entity_type: "garden",
      lon: 120.5044475,
      lat: 31.2547028,
      confidence: "exact",
      basis: "OpenStreetMap 当前地物中心点",
      geometry_type: "point",
      uncertainty_radius_m: null,
      area_coordinates: [],
      extent_source: null,
      extent_basis: null,
      coordinate_system: "WGS84",
      dynasties: ["qing", "modern"],
      heritage_status: "extant",
      access_status: "ticket_or_hours",
      summary: "现存园林。",
      address: "木渎镇山塘街",
      evidence: [evidence],
      start_year: 1736,
      end_year: null,
    },
    {
      id: "pt-yongan-bridge",
      entity_id: "entity-bridge-yongan",
      name: "永安桥",
      entity_type: "bridge",
      lon: 120.5043797,
      lat: 31.2540876,
      confidence: "approximate",
      basis: "文字地址与未命名桥位交叉对应",
      geometry_type: "uncertainty_radius",
      uncertainty_radius_m: 750,
      area_coordinates: [],
      extent_source: "editorial_estimate",
      extent_basis: "依据文字地址生成的候选范围，不代表历史边界或统计概率。",
      coordinate_system: "WGS84",
      dynasties: ["ming", "qing", "modern"],
      heritage_status: "extant",
      access_status: "view_only",
      summary: "现存石桥，坐标待实地复核。",
      address: "严家花园前",
      evidence: [evidence],
      start_year: 1497,
      end_year: null,
    },
  ],
  layers: [
    {
      id: "osm-current",
      name: "OpenStreetMap 现代底图",
      kind: "base",
      available: true,
      source_url: "https://www.openstreetmap.org/copyright",
      attribution: "© OpenStreetMap contributors",
      calibration_note: "现代底图，仅用于现状位置参照。",
      tile_url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    },
    {
      id: "pingjiang-map-reference",
      name: "《平江图》（1229）公开影像参考",
      kind: "historical",
      available: false,
      source_url: "https://www.loc.gov/item/2003626507/",
      attribution: "Library of Congress",
      calibration_note: "未完成木渎区域控制点校准，暂不叠加。",
      tile_url: null,
    },
  ],
  events: [
    {
      id: "event-yongan-built",
      title: "永安桥始建",
      year_start: 1497,
      year_end: 1497,
      time_label: "明弘治十年（1497）",
      precision: "exact",
      point_id: "pt-yongan-bridge",
      summary: "始建",
      featured: true,
      importance: "landmark",
      participants: [
        { id: "person-fuchao", name: "傅潮", entity_type: "person" },
      ],
      evidence: [evidence],
    },
    {
      id: "event-yan-duan-garden",
      title: "严家花园前身改称端园",
      year_start: 1828,
      year_end: 1828,
      time_label: "清道光八年（1828）",
      precision: "exact",
      point_id: "pt-yan-garden",
      summary: "沈氏后人出售后，钱照购得并改称端园。",
      featured: true,
      importance: "notable",
      evidence: [evidence],
    },
  ],
  relations: [
    {
      id: "relation-yongan-fuchao",
      subject_id: "entity-bridge-yongan",
      subject_name: "永安桥",
      subject_type: "bridge",
      relation_type: "built_by",
      object_id: "person-fuchao",
      object_name: "傅潮",
      object_type: "person",
      start_time: "1497",
      end_time: null,
      confidence: 0.85,
      evidence: [evidence],
    },
  ],
  trajectories: [
    {
      id: "trajectory-qianlong",
      person_id: "person-qianlong",
      person_name: "乾隆帝",
      summary: "仅展示可核验活动节点。",
      has_uncertain_segments: true,
      disclaimer: "虚线不表示真实行进道路。",
      points: [
        {
          id: "node-1",
          point_id: "pt-yan-garden",
          year_start: 1751,
          year_end: 1784,
          time_label: "乾隆南巡时期",
          label: "木渎活动线索",
          confidence: "approximate",
          evidence: [evidence],
        },
      ],
    },
  ],
  routes: [
    {
      id: "route-gardens",
      name: "山塘街半日研学",
      duration: "half_day",
      audience: "中学生",
      summary: "观察园林与桥梁。",
      stop_ids: ["pt-yan-garden", "pt-yongan-bridge"],
      disclaimer: "不是实时导航，出发前核验开放状态。",
      evidence: [evidence],
    },
  ],
};

async function mockMapPage(page: Page) {
  mockLangGraphAPI(page);
  await page.route("**/api/map/catalog", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(catalog),
    }),
  );
  await page.route("https://tile.openstreetmap.org/**", (route) =>
    route.abort("failed"),
  );
}

test("desktop exploration keeps the map primary and shows one traceable detail surface", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockMapPage(page);

  await page.goto("/workspace/map");
  await expect(page.getByRole("heading", { name: "古舆地图" })).toBeVisible();
  await expect(page.getByText("2 个可追溯点位")).toBeVisible();

  const modeTabs = page.getByRole("tablist", { name: "地图模式" });
  const explorationTab = page.getByRole("tab", { name: "空间探索" });
  const routeTab = page.getByRole("tab", {
    name: "研学路线",
    includeHidden: true,
  });
  await expect(modeTabs).toBeVisible();
  await expect(explorationTab).toHaveAttribute("aria-selected", "true");
  await expect(routeTab).toHaveAttribute("aria-selected", "false");
  await expect(page.getByRole("region", { name: "研学路线" })).toBeHidden();

  const mapCanvas = page.getByLabel("古舆地图画布");
  await expect(mapCanvas).toBeInViewport();
  const mapBox = await mapCanvas.boundingBox();
  const viewport = page.viewportSize();
  expect(mapBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(mapBox!.width).toBeGreaterThan(viewport!.width * 0.45);

  const pointDetails = page.getByRole("region", { name: "点位详情" });
  await expect(pointDetails).toHaveCount(0);
  await page
    .getByRole("button", { name: "查看历史事件：严家花园前身改称端园" })
    .click();
  await expect(
    page
      .getByRole("region", { name: "历史时间轴" })
      .locator("strong")
      .getByText("清道光八年（1828）", { exact: true }),
  ).toBeVisible();

  const yanGardenMarker = page.getByRole("button", {
    name: "地图点位 严家花园",
  });
  const yonganBridgeMarker = page.getByRole("button", {
    name: "地图范围 永安桥",
  });
  await expect(yonganBridgeMarker).toHaveAttribute(
    "data-spatial-geometry",
    "uncertainty_radius",
  );
  await expect(yanGardenMarker).toHaveAttribute("data-label-visible", "false");
  await expect(yonganBridgeMarker).toHaveAttribute(
    "data-label-visible",
    "false",
  );
  await expect(
    yonganBridgeMarker.locator('[data-map-marker-label="true"]'),
  ).not.toBeVisible();

  await yonganBridgeMarker.hover();
  await expect(yonganBridgeMarker).toHaveAttribute(
    "data-label-visible",
    "true",
  );
  await page.getByRole("heading", { name: "古舆地图" }).hover();
  await expect(yonganBridgeMarker).toHaveAttribute(
    "data-label-visible",
    "false",
  );

  await yonganBridgeMarker.click();
  await expect(
    pointDetails.getByRole("heading", { name: "永安桥" }),
  ).toBeVisible();
  await expect(
    pointDetails.getByText("估计中心", { exact: true }),
  ).toBeVisible();
  await expect(pointDetails.getByText("约 750 米的不确定范围")).toBeVisible();
  await pointDetails.getByRole("tab", { name: "沿革" }).click();
  await expect(pointDetails.getByText("永安桥由傅潮营建")).toBeVisible();
  await pointDetails.getByRole("tab", { name: "来源" }).click();
  await expect(
    pointDetails.getByRole("link", {
      name: /严家花园 OpenStreetMap 要素/,
    }),
  ).toHaveAttribute("href", evidence.url);
  await expect(page.getByRole("region", { name: "历史时间轴" })).toHaveCount(1);
  await expect(page.locator('section[aria-label$="时间轴大事记"]')).toHaveCount(
    0,
  );
  await expect
    .poll(async () => {
      const markerBox = await yonganBridgeMarker.boundingBox();
      const currentMapBox = await mapCanvas.boundingBox();
      if (!markerBox || !currentMapBox) return Number.POSITIVE_INFINITY;
      return Math.abs(
        markerBox.x +
          markerBox.width / 2 -
          (currentMapBox.x + currentMapBox.width / 2),
      );
    })
    .toBeLessThan(48);
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(yonganBridgeMarker).toHaveAttribute(
    "data-label-visible",
    "true",
  );

  await page.getByRole("button", { name: "筛选点位" }).click();
  const filters = page.getByLabel("地图筛选");
  await expect(filters).toBeVisible();
  await expect(page.getByText("当前筛选结果（2）")).toBeVisible();
  await page.getByLabel("关键词").fill("桥");
  await expect(page.getByText("当前筛选结果（2）")).toBeVisible();
  await page.getByRole("button", { name: "应用筛选" }).click();
  await expect(page.getByText("当前筛选结果（1）")).toBeVisible();
  await page
    .getByRole("region", { name: "当前筛选结果" })
    .getByRole("button", { name: /永安桥/ })
    .click();
  await expect(
    pointDetails.getByRole("heading", { name: "永安桥" }),
  ).toBeVisible();

  await expect(
    page.getByText("暂无授权 GLB 三维模型", { exact: true }),
  ).toHaveCount(0);
  await expect(page.locator("[data-glb-id]")).toHaveCount(0);

  const mapLegend = page.locator('[data-map-legend="true"]');
  const mapError = page.locator('[data-map-error="true"]');
  await expect(mapError).toBeVisible();
  const legendBox = await mapLegend.boundingBox();
  const errorBox = await mapError.boundingBox();
  expect(legendBox).not.toBeNull();
  expect(errorBox).not.toBeNull();
  const overlaps = !(
    legendBox!.y + legendBox!.height <= errorBox!.y ||
    errorBox!.y + errorBox!.height <= legendBox!.y ||
    legendBox!.x + legendBox!.width <= errorBox!.x ||
    errorBox!.x + errorBox!.width <= legendBox!.x
  );
  expect(overlaps).toBe(false);
});

test("featured timeline playback focuses each event and opens its map bubble", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockMapPage(page);

  await page.goto("/workspace/map");
  await expect(
    page.getByRole("button", {
      name: "历史事件：明弘治十年（1497），永安桥始建",
    }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(page.getByLabel("历史故事镜头", { exact: true })).toBeVisible();
  await expect(
    page
      .getByLabel("历史故事镜头", { exact: true })
      .getByText("史料记载：始建", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("历史故事镜头", { exact: true })
      .getByText("相关人物：傅潮", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("历史故事镜头", { exact: true })
      .getByText("公开条目记载永安桥始建。"),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("历史故事镜头", { exact: true })
      .getByText("暂无授权影像、碑刻拓本或三维模型"),
  ).toBeVisible();
  await expect(page.getByLabel("古舆地图画布")).toHaveAttribute(
    "data-map-camera-pitch",
    "42",
  );
  await expect(page.getByText("始建", { exact: true })).toBeVisible();

  const timelineScale = page.locator('[data-timeline-scale-start="1497"]');
  await expect(timelineScale).toHaveAttribute(
    "data-timeline-scale-end",
    "1828",
  );
  const earlyEventBox = await page
    .getByRole("button", { name: "查看历史事件：永安桥始建" })
    .boundingBox();
  const lateEventBox = await page
    .getByRole("button", { name: "查看历史事件：严家花园前身改称端园" })
    .boundingBox();
  expect(earlyEventBox).not.toBeNull();
  expect(lateEventBox).not.toBeNull();
  expect(Math.abs(lateEventBox!.x - earlyEventBox!.x)).toBeGreaterThan(500);

  await page.getByRole("button", { name: "播放时间轴" }).click();
  await expect(
    page.getByRole("button", {
      name: "历史事件：清道光八年（1828），严家花园前身改称端园",
    }),
  ).toBeVisible({ timeout: 5_000 });
  await expect(
    page
      .getByLabel("历史故事镜头", { exact: true })
      .getByText("史料记载：沈氏后人出售后，钱照购得并改称端园。", {
        exact: true,
      }),
  ).toBeVisible();
});

test("map layer controls keep modern positioning optional and flag uncalibrated history", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockMapPage(page);

  await page.goto("/workspace/map");
  await expect(page.getByRole("heading", { name: "古舆地图" })).toBeVisible();
  await page.getByRole("button", { name: "地图图层" }).click();

  await expect(
    page.getByRole("heading", { name: "图层与人物轨迹" }),
  ).toBeVisible();
  const modernLayer = page.getByRole("checkbox", {
    name: "显示OpenStreetMap 现代底图",
  });
  await expect(modernLayer).toBeChecked();
  await modernLayer.uncheck();
  await expect(modernLayer).not.toBeChecked();
  await expect(page.getByText("待校准", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("checkbox", {
      name: "显示《平江图》（1229）公开影像参考",
    }),
  ).toBeDisabled();
});

test("route mode reveals the editable study route and exports its outline", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockMapPage(page);

  await page.goto("/workspace/map");
  const routeTab = page.getByRole("tab", {
    name: "研学路线",
    includeHidden: true,
  });
  const routeRegion = page.getByRole("region", { name: "研学路线" });
  await expect(routeTab).toHaveAttribute("aria-selected", "false");
  await expect(routeRegion).toBeHidden();

  await routeTab.click();
  await expect(routeTab).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("tab", { name: "空间探索", includeHidden: true }),
  ).toHaveAttribute("aria-selected", "false");
  await expect(routeRegion).toBeVisible();
  await expect(
    routeRegion.getByRole("button", { name: "严家花园", exact: true }),
  ).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await routeRegion.getByRole("button", { name: "导出研学提纲" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("山塘街半日研学.md");
});

test("live location remains visible while exploring and following a study route", async ({
  context,
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await context.grantPermissions(["geolocation"], {
    origin: appOrigin,
  });
  await context.setGeolocation({ longitude: 120.5042, latitude: 31.2544 });
  await mockMapPage(page);

  await page.goto("/workspace/map");
  await page.getByRole("button", { name: "开启实时定位" }).click();

  const userMarker = page.getByLabel(/我的实时位置/);
  await expect(userMarker).toBeVisible();
  await expect(userMarker).toHaveAttribute("data-location-lon", "120.504200");
  await expect(page.getByText("实时定位中")).toBeVisible();

  await context.setGeolocation({ longitude: 120.5048, latitude: 31.2551 });
  await expect(userMarker).toHaveAttribute("data-location-lon", "120.504800");
  await expect(userMarker).toHaveAttribute("data-location-lat", "31.255100");

  await page.getByRole("tab", { name: "研学路线" }).click();
  await expect(page.getByRole("region", { name: "研学路线" })).toBeVisible();
  await expect(userMarker).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "山塘街半日研学" }),
  ).toBeVisible();
});

test("mobile point selection brings its details into view immediately", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockMapPage(page);

  await page.goto("/workspace/map");
  await expect(page.getByRole("tab", { name: "空间探索" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  const marker = page.getByRole("button", { name: "地图范围 永安桥" });
  await expect(marker).toBeVisible();
  await marker.click({ force: true });

  const pointDetails = page.getByRole("region", { name: "点位详情" });
  const pointTitle = pointDetails.getByRole("heading", { name: "永安桥" });
  await expect(pointDetails).toBeVisible();
  await expect(pointDetails).toBeInViewport();
  await expect(pointTitle).toBeInViewport();
  await expect(
    page.getByText("暂无授权 GLB 三维模型", { exact: true }),
  ).toHaveCount(0);
});
