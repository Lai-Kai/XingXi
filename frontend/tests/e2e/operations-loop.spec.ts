import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const dashboard = {
  answer_accuracy_rate: 0.875,
  citation_rate: 0.92,
  refusal_compliance_rate: 1,
  user_satisfaction_rate: 0.8,
  answer_count: 40,
  unanswered_count: 3,
  map_point_click_count: 26,
  manual_correction_count: 4,
  three_dimensional_load_success_rate: null,
  hot_entities: [
    { entity_id: "entity-mudu", name: "木渎古镇", views: 18 },
    { entity_id: "entity-yan", name: "严家花园", views: 11 },
  ],
};

test("operations workspace exposes the non-3d governance loop", async ({
  page,
}, testInfo) => {
  mockLangGraphAPI(page);
  await page.route("**/api/operations/dashboard?*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dashboard),
    }),
  );
  await page.route("**/api/operations/evaluations/cases", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/operations/evaluations/runs", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/operations/corrections", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/operations/asset-versions", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );

  await page.goto("/workspace/operations");
  await expect(page.getByRole("heading", { name: "运营中心" })).toBeVisible();
  await expect(page.getByText("87.5%")).toBeVisible();
  await expect(page.getByText("三维完成后启用")).toBeVisible();
  await expect(page.getByText("木渎古镇")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("operations-desktop.png"),
    fullPage: true,
  });

  await page.setViewportSize({ width: 1024, height: 768 });
  await expect(page.getByRole("button", { name: "回归评测" })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("operations-laptop.png"),
    fullPage: true,
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByText("回答准确率")).toBeVisible();
  await expect(page.getByText("地图点位点击")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("operations-mobile.png"),
    fullPage: true,
  });
});
