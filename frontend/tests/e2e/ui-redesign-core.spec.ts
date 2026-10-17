import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { MAP_MODEL_ASSETS } from "../../src/core/map/model-assets";

import { mockLangGraphAPI, MOCK_THREAD_ID } from "./utils/mock-api";

const screenshots = process.env.UI_CORE_DIR;
const aiText =
  "## 香溪与木渎的历史线索\n\n研究需要区分原文记载与后世解释。先核对方志的卷次、版本与页码，再讨论水系与聚落的关系。\n\n参见 [citation:康熙吴县志](evidence://evidence-a)，并与 [citation:木渎志](evidence://evidence-b) 对读。\n\n目前可见的资料能说明河道与街巷的联系，具体位置仍应结合原件与现状资料继续核对。";
const source = {
  evidence_id: "evidence-a",
  document_id: "document-a",
  document_title: "（康熙）吴县志",
  chunk_id: "chunk-a",
  page_start: 12,
  page_end: 13,
  quote: "木渎水系原文摘录。",
};
const feed = (day = "2026-10-15", title = "香溪水系与木渎古镇") => ({
  kind: "daily_grounded",
  generated_for: day,
  next_refresh_at: "2026-10-16T00:00:00+08:00",
  items: [
    {
      id: "water",
      title,
      summary: "对读方志中的水系记载，核对河道、古桥与街巷之间的联系。",
      tag: "方志考据",
      source_basis: "已发布文献",
      prompt: `考证${title}`,
      retrieval_query: "木渎 香溪",
      origin: "evidence_backed_fallback",
      evidence_count: 1,
      knowledge_release_id: "release-fixture",
      popularity_users: null,
      popularity_searches: null,
      sources: [source],
    },
    {
      id: "garden",
      title: "园林题咏与地景名称沿革",
      summary: "从诗文与方志所见地景出发，辨析不同版本中的名称差异。",
      tag: "人物与园林",
      source_basis: "已发布文献",
      prompt: "考证园林题咏",
      retrieval_query: "木渎 园林",
      origin: "evidence_backed_fallback",
      evidence_count: 1,
      knowledge_release_id: "release-fixture",
      popularity_users: null,
      popularity_searches: null,
      sources: [
        { ...source, evidence_id: "evidence-b", document_title: "木渎志" },
      ],
    },
  ],
});
const detail = (id: string) => ({
  evidence_id: id,
  chunk_id: `chunk-${id}`,
  document_id: "document-a",
  source_file_id: "file-a",
  document_title: id === "evidence-a" ? "（康熙）吴县志" : "木渎志",
  edition: "馆藏版本待实物核对",
  volume: "卷十二",
  section: "水利",
  page_start: 12,
  page_end: 13,
  folio_start: "六上",
  folio_end: "六下",
  quote:
    id === "evidence-a"
      ? "香溪自山间而来，经镇而东。\n此处为软件测试引文。"
      : "木渎沿河成市。此处为第二条软件测试引文。",
  source_level: "B",
  review_status: "reviewed",
  href: `evidence://${id}`,
});
const mapSource = {
  id: "map-source-a",
  title: "方志地理条目（测试夹具）",
  publisher: "测试馆藏",
  url: "https://example.test/source",
  kind: "local_gazetteer",
  retrieved_at: "2026-10-15",
  quote: "测试史料引文，不代表生产语料。",
};
const asset = MAP_MODEL_ASSETS[0]!;
const mapCatalog = {
  updated_at: "2026-10-15",
  data_notice: "软件测试目录，模型为生成示意，未作史实核验。",
  points: [
    {
      id: asset.pointId,
      entity_id: asset.entityId,
      name: "木渎古镇",
      entity_type: "historic_district",
      lon: 120.5044,
      lat: 31.2547,
      confidence: "exact",
      basis: "测试现状地物定位",
      geometry_type: "point",
      uncertainty_radius_m: null,
      area_coordinates: [],
      extent_source: null,
      extent_basis: null,
      coordinate_system: "WGS84",
      dynasties: ["ming", "qing", "modern"],
      heritage_status: "extant",
      access_status: "view_only",
      summary: "依照资料核对古镇、街巷与水系关系。",
      address: "木渎镇",
      evidence: [mapSource],
      review_status: "reviewed",
      release_id: "release-fixture",
      record_kind: "reference",
      start_year: 1400,
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
      calibration_note: "现状底图",
      tile_url: "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
    },
  ],
  events: [
    {
      id: "event-a",
      title: "方志记载水系",
      year_start: 1500,
      year_end: 1500,
      time_label: "明 · 1500年",
      precision: "exact",
      point_id: asset.pointId,
      summary: "测试事件，用于检查时间轴与证据联动。",
      evidence: [mapSource],
      review_status: "reviewed",
      record_kind: "reference",
      featured: true,
      importance: "landmark",
      participants: [
        { id: "person-fixture", name: "登记人物甲", entity_type: "person" },
      ],
    },
    {
      id: "event-b",
      title: "古镇街巷续记",
      year_start: 1700,
      year_end: 1700,
      time_label: "清 · 1700年",
      precision: "exact",
      point_id: asset.pointId,
      summary: "第二个测试事件。",
      evidence: [mapSource],
      review_status: "reviewed",
      record_kind: "reference",
      featured: true,
      importance: "notable",
    },
  ],
  routes: [],
  trajectories: [],
  relations: [],
};

async function mockCore(page: Page) {
  await page.route("**/api/**", (route) =>
    route.fulfill({ status: 503, json: { detail: "本轮测试：服务暂不可用" } }),
  );
  mockLangGraphAPI(page, {
    threads: [
      {
        thread_id: MOCK_THREAD_ID,
        title: "香溪水系文史考据",
        updated_at: "2026-10-15T01:00:00Z",
        messages: [
          {
            type: "human",
            id: "human-a",
            content: "请考证香溪水系与木渎古镇的关系。",
          },
          { type: "ai", id: "answer-a", content: aiText },
        ],
      },
    ],
  });
  await page.route("**/api/models", (route) =>
    route.fulfill({
      json: {
        models: [
          {
            id: "xingxi-test",
            name: "xingxi-test",
            model: "xingxi-test",
            display_name: "星羲测试模型",
            supports_thinking: false,
            supports_reasoning_effort: false,
          },
        ],
        token_usage: { enabled: false },
      },
    }),
  );
  await page.route("**/api/research-feed/daily?**", (route) =>
    route.fulfill({ json: feed() }),
  );
  await page.route("**/api/research-feed/history?**", (route) =>
    route.fulfill({
      json: {
        kind: "daily_grounded_history",
        current: feed(),
        previous: [feed("2026-10-14", "往日古桥课题")],
        history_days: 2,
      },
    }),
  );
  await page.route("**/api/knowledge-search/evidence/*", (route) =>
    route.fulfill({
      json: detail(
        decodeURIComponent(
          new URL(route.request().url()).pathname.split("/").at(-1)!,
        ),
      ),
    }),
  );
  await page.route("**/api/map/catalog", (route) =>
    route.fulfill({ json: mapCatalog }),
  );
  await page.route("**/api/map/reference-points?**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("https://tile.openstreetmap.de/**", (route) =>
    route.abort(),
  );
}
async function capture(page: Page, name: string) {
  if (!screenshots) return;
  await mkdir(screenshots, { recursive: true });
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
  });
  await page.screenshot({
    path: resolve(screenshots, `${name}.png`),
    animations: "disabled",
  });
  await writeFile(
    resolve(screenshots, `${name}.json`),
    JSON.stringify(
      await page.evaluate(() => ({
        url: location.href,
        viewport: { width: innerWidth, height: innerHeight },
        documentWidth: document.documentElement.scrollWidth,
        theme: document.documentElement.className,
        data: "Mock API; actual local model asset when opened",
        mapStatus:
          document
            .querySelector("[data-map-status]")
            ?.getAttribute("data-map-status") ?? null,
      })),
      null,
      2,
    ),
  );
}
test.beforeEach(async ({ page }) => {
  await mockCore(page);
});
for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 360, height: 800 },
]) {
  for (const theme of ["light", "dark"]) {
    test(`core surfaces ${viewport.width} ${theme}`, async ({ page }) => {
      test.setTimeout(90000);
      await page.setViewportSize(viewport);
      await page.addInitScript(
        (value) => localStorage.setItem("theme", value),
        theme,
      );
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto("/workspace");
      await expect(
        page.getByRole("heading", { name: "香溪水系与木渎古镇" }),
      ).toBeVisible();
      const hero = page.locator(".research-hero img");
      await expect(hero).toBeVisible();
      await expect
        .poll(() =>
          hero.evaluate((node) => (node as HTMLImageElement).naturalWidth),
        )
        .toBeGreaterThan(0);
      await capture(page, `home-${viewport.width}-${theme}`);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(viewport.width);
      await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);
      const citation = page.locator('a[data-evidence-id="evidence-a"]').first();
      await expect(citation).toBeVisible();
      await expect(citation).toHaveAttribute(
        "href",
        /\/workspace\/library\?evidence_id=evidence-a/,
      );
      if (viewport.width < 1280)
        await expect(page.getByRole("dialog")).toHaveCount(0);
      await citation.click();
      const evidence = page.locator('[data-evidence-detail-id="evidence-a"]');
      await expect(
        evidence.getByText("香溪自山间而来，经镇而东。", { exact: false }),
      ).toBeVisible();
      await expect(evidence.getByText("卷十二", { exact: true })).toBeVisible();
      expect(new URL(page.url()).pathname).toBe(
        `/workspace/chats/${MOCK_THREAD_ID}`,
      );
      if (viewport.width >= 1280)
        expect(
          (await page
            .getByRole("complementary", { name: "史料考据视窗", exact: true })
            .boundingBox())!.width,
        ).toBe(380);
      else {
        const dialog = page.getByRole("dialog");
        await expect(dialog).toBeVisible();
        if (viewport.width < 768)
          expect((await dialog.boundingBox())!.height).toBeCloseTo(
            viewport.height * 0.65,
            0,
          );
      }
      await capture(page, `chat-evidence-${viewport.width}-${theme}`);
      if (viewport.width < 768) {
        const handle = page.getByRole("button", {
          name: "下滑关闭史料考据视窗",
        });
        await expect(handle).toBeVisible();
        // Wait for the sheet's entry animation before taking manual drag coordinates.
        await handle.click({ trial: true });
        const box = (await handle.boundingBox())!;
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.down();
        await page.mouse.move(
          box.x + box.width / 2,
          box.y + box.height / 2 + 90,
          { steps: 6 },
        );
        await page.mouse.up();
        await expect(page.getByRole("dialog")).toBeHidden();
        await expect(citation).toBeFocused();
        await citation.press("Enter");
      }
      await page
        .getByRole("button", { name: "关闭史料考据视窗", exact: true })
        .click();
      await expect(citation).toBeFocused();
      if (viewport.width < 1280) {
        await expect(page.getByRole("dialog")).toBeHidden();
        await expect(citation).toBeFocused();
      }
      await page.goto("/workspace/map");
      await expect(
        page.getByRole("slider", { name: "历史纪年" }),
      ).toBeVisible();
      await expect(
        page.getByText("OpenStreetMap", { exact: false }).first(),
      ).toBeVisible();
      const marker = page.getByRole("button", { name: /地图点位 木渎古镇/ });
      await marker.click();
      await expect(
        page.getByRole("tab", { name: "史料考据", exact: true }),
      ).toBeVisible();
      await page.getByRole("tab", { name: "关联人物", exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "登记人物甲", exact: true }),
      ).toBeVisible();
      await capture(page, `map-person-${viewport.width}-${theme}`);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(viewport.width);
      expect(errors).toEqual([]);
    });
  }
}
test("home composer protects IME and feed tabs support keyboard and history dates", async ({
  page,
}) => {
  await page.goto("/workspace");
  const query = page.getByLabel("研究问题");
  await query.fill("木渎方志");
  await query.dispatchEvent("keydown", { key: "Enter", isComposing: true });
  await expect(page).toHaveURL(/\/workspace$/);
  await page.getByRole("tab", { name: "今日选题", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(
    page.getByRole("tab", { name: "最新收录", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Home");
  await page.getByRole("button", { name: "查看更多今日与往日选题" }).click();
  await page.getByLabel("选题日期").selectOption("2026-10-14");
  await expect(
    page.getByRole("heading", { name: "往日古桥课题" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "香溪水系与木渎古镇" }),
  ).toHaveCount(0);
  await query.fill("木渎水系");
  await query.press("Enter");
  await page.waitForURL(/\/workspace\/chats\/new\?/);
  expect(new URL(page.url()).searchParams.get("prompt")).toBe("木渎水系");
});
test("evidence errors recover and late previous responses cannot replace the selected source", async ({
  page,
}) => {
  let attempts = 0;
  await page.route("**/api/knowledge-search/evidence/evidence-a", (route) => {
    attempts++;
    return attempts === 1
      ? route.fulfill({ status: 503, json: { detail: "出处服务暂不可用" } })
      : route.fulfill({ json: detail("evidence-a") });
  });
  await page.goto(`/workspace/chats/${MOCK_THREAD_ID}`);
  await page.locator('a[data-evidence-id="evidence-a"]').first().click();
  await expect(
    page.getByRole("alert").filter({ hasText: "暂无法打开" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "重新加载出处" }).click();
  await expect(
    page
      .locator('[data-evidence-detail-id="evidence-a"]')
      .getByText(/香溪自山间/),
  ).toBeVisible();
  let release: (() => void) | undefined;
  let finished: (() => void) | undefined;
  const oldFinished = new Promise<void>((resolve) => {
    finished = resolve;
  });
  await page.route(
    "**/api/knowledge-search/evidence/evidence-a",
    async (route) => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      await route
        .fulfill({ json: detail("evidence-a") })
        .catch(() => undefined);
      finished?.();
    },
  );
  await page.locator('a[data-evidence-id="evidence-b"]').first().click();
  const requested = page.waitForRequest(
    "**/api/knowledge-search/evidence/evidence-a",
  );
  await page.locator('a[data-evidence-id="evidence-a"]').first().click();
  await requested;
  await page.locator('a[data-evidence-id="evidence-b"]').first().click();
  await expect(
    page
      .locator('[data-evidence-detail-id="evidence-b"]')
      .getByText(/木渎沿河成市/),
  ).toBeVisible();
  release?.();
  await oldFinished;
  await expect(
    page
      .locator('[data-evidence-detail-id="evidence-b"]')
      .getByText(/木渎沿河成市/),
  ).toBeVisible();
});
test("map year slider is keyboard operable and preserves the cached catalog", async ({
  page,
}) => {
  let loads = 0;
  await page.route("**/api/map/catalog", (route) => {
    loads++;
    return route.fulfill({ json: mapCatalog });
  });
  await page.goto("/workspace/map");
  const slider = page.getByRole("slider", { name: "历史纪年" });
  await slider.focus();
  await slider.press("Home");
  await slider.press("ArrowRight");
  await expect(slider).not.toHaveAttribute("aria-valuetext", "全部年代");
  await page.getByRole("button", { name: "全部年代", exact: true }).click();
  await expect(slider).toHaveAttribute("aria-valuetext", "全部年代");
  await page.getByRole("button", { name: "上一个历史事件" }).click();
  await expect(
    page.getByRole("heading", { name: "古镇街巷续记", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "全部年代", exact: true }).click();
  await page.getByRole("button", { name: "下一个历史事件" }).click();
  await expect(
    page.getByRole("heading", { name: "方志记载水系", exact: true }),
  ).toBeVisible();
  expect(loads).toBe(1);
});

test("model study keeps one real viewer through rotation, enlargement and mobile layout", async ({
  page,
}) => {
  test.setTimeout(90000);
  let downloads = 0;
  page.on("request", (request) => {
    if (request.url().includes(asset.src!)) downloads++;
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/workspace/map");
  const marker = page.getByRole("button", { name: /地图点位 木渎古镇/ });
  await marker.focus();
  await marker.press("Enter");
  expect(downloads).toBe(0);
  const modelTab = page.getByRole("tab", { name: /^3D 建筑研习/ });
  await modelTab.click();
  await expect(page.locator('[data-model-state="ready"]')).toBeVisible({
    timeout: 45000,
  });
  await expect(page.locator("model-viewer")).toHaveCount(1);
  await page.getByRole("button", { name: "自动旋转", exact: true }).click();
  await expect(page.locator("model-viewer")).toHaveAttribute("auto-rotate", "");
  await page.getByRole("button", { name: "复位", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "自动旋转", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await capture(page, "map-model-1440-light");
  await page.getByRole("button", { name: "放大查看模型" }).click();
  await expect(page.getByRole("dialog").locator("model-viewer")).toHaveCount(1);
  await expect(page.locator("model-viewer")).toHaveCount(1);
  expect(downloads).toBe(1);
  await capture(page, "map-model-expanded-1440-light");
  await page.getByRole("button", { name: "返回点位详情", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("model-viewer")).toHaveCount(0);
  await marker.focus();
  await marker.press("Enter");
  await modelTab.click();
  await expect(page.locator('[data-model-state="ready"]')).toBeVisible({
    timeout: 45000,
  });
  await expect(page.locator("model-viewer")).toHaveCount(1);
  await capture(page, "map-model-390-light");
});

test("coarse pointer research controls and portal model actions reach 44 pixels", async ({
  browser,
}) => {
  test.setTimeout(90000);
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    hasTouch: true,
    isMobile: true,
  });
  try {
    const page = await context.newPage();
    await mockCore(page);
    const target = async (locator: ReturnType<Page["locator"]>) => {
      await expect(locator).toBeVisible();
      // Measure the resting target after the existing Dialog entrance scale.
      await expect
        .poll(async () => (await locator.boundingBox())?.width ?? 0)
        .toBeGreaterThanOrEqual(44);
      await expect
        .poll(async () => (await locator.boundingBox())?.height ?? 0)
        .toBeGreaterThanOrEqual(44);
    };
    await page.goto(
      `${process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3106"}/workspace/chats/${MOCK_THREAD_ID}`,
    );
    expect(
      await page.evaluate(() => matchMedia("(pointer: coarse)").matches),
    ).toBe(true);
    const citation = page.locator('a[data-evidence-id="evidence-a"]').first();
    await target(citation);
    await citation.tap();
    await target(
      page.getByRole("button", { name: "关闭史料考据视窗", exact: true }),
    );
    await page
      .getByRole("button", { name: "关闭史料考据视窗", exact: true })
      .tap();
    await page.goto(
      `${process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3106"}/workspace/map`,
    );
    await target(page.getByRole("button", { name: "筛选点位", exact: true }));
    await target(page.getByRole("button", { name: "Zoom in", exact: true }));
    const marker = page.getByRole("button", { name: /地图点位 木渎古镇/ });
    await target(marker);
    await marker.tap();
    await page.getByRole("tab", { name: /^3D 建筑研习/ }).tap();
    await expect(page.locator('[data-model-state="ready"]')).toBeVisible({
      timeout: 45000,
    });
    await target(page.getByRole("button", { name: "放大查看模型" }));
    await target(page.getByRole("button", { name: "自动旋转", exact: true }));
    await page.getByRole("button", { name: "放大查看模型" }).tap();
    await target(
      page.getByRole("button", { name: "返回点位详情", exact: true }),
    );
    await target(
      page
        .locator(".research-model-dialog")
        .getByRole("button", { name: "Close", exact: true }),
    );
    await expect(page.locator("model-viewer")).toHaveCount(1);
  } finally {
    await context.close();
  }
});

// Explicit opt-in only: normal deterministic tests retain the offline-tile path.
if (process.env.UI_LIVE_OSM === "1") {
  test("real OSM tiles remain original beneath the floating research console", async ({
    page,
  }) => {
    test.setTimeout(90000);
    let successfulTiles = 0;
    page.on("response", (response) => {
      if (
        response.url().startsWith("https://tile.openstreetmap.de/") &&
        response.ok()
      )
        successfulTiles++;
    });
    await page.route("https://tile.openstreetmap.de/**", (route) =>
      route.continue(),
    );
    await page.route("**/api/map/catalog", (route) =>
      route.fulfill({
        json: {
          ...mapCatalog,
          layers: mapCatalog.layers.map((layer) => ({
            ...layer,
            attribution:
              '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>',
          })),
        },
      }),
    );
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(viewport);
      await page.goto("/workspace/map");
      await expect(page.locator("[data-map-status]")).toHaveAttribute(
        "data-map-status",
        "ready",
        { timeout: 30000 },
      );
      await expect.poll(() => successfulTiles).toBeGreaterThan(0);
      await expect(page.locator("[data-map-error]")).toHaveCount(0);
      await expect(page.locator(".maplibregl-canvas")).toHaveCSS(
        "filter",
        "none",
      );
      await expect(page.locator("[data-map-base-opacity]")).toHaveAttribute(
        "data-map-base-opacity",
        "1",
      );
      await expect(
        page.getByRole("link", { name: "OpenStreetMap contributors" }),
      ).toBeVisible();
      if (viewport.width === 1440) {
        await page.getByRole("button", { name: /地图点位 木渎古镇/ }).click();
        await page.getByRole("tab", { name: /^3D 建筑研习/ }).click();
        await expect(page.locator('[data-model-state="ready"]')).toBeVisible({
          timeout: 45000,
        });
      }
      await page.mouse.move(0, 0);
      await capture(page, `map-live-${viewport.width}-light`);
    }
  });
}
