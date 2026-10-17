import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const reportDir = process.env.TEST_REPORT_DIR ?? "test-results";
const preview = process.env.FOUNDATION_PREVIEW_PATH;

async function openFixture(page: Page, theme: string) {
  test.skip(
    !preview,
    "Generate the opt-in SSR fixture with the foundation unit tests first.",
  );
  const response = await page.request.get("/workspace");
  expect(response.ok()).toBe(true);
  const html = await response.text();
  const styles = [...html.matchAll(/<link[^>]+>/g)]
    .filter(([tag]) => tag.includes('rel="stylesheet"'))
    .map(([tag]) => /href="([^"]+)"/.exec(tag)?.[1])
    .filter((href): href is string => Boolean(href))
    .map(
      (href) =>
        `<link rel="stylesheet" href="${new URL(href, response.url())}">`,
    )
    .join("");
  expect(styles).not.toBe("");
  await page.setContent(`<html lang="zh-CN" class="${theme}"><head>
    <meta name="viewport" content="width=device-width, initial-scale=1">${styles}
    </head><body>${await readFile(preview!, "utf8")}</body></html>`);
  await page.evaluate(() => document.fonts.ready);
  // Linked production CSS can start finite transitions on a freshly inserted
  // SSR fixture. Measure the settled state, leaving continuous skeletons alone.
  await page.evaluate(async () => {
    await new Promise<void>((done) =>
      requestAnimationFrame(() => requestAnimationFrame(() => done())),
    );
    await Promise.all(
      document
        .getAnimations()
        .filter(
          (animation) => animation.effect?.getTiming().iterations !== Infinity,
        )
        .map((animation) => animation.finished.catch(() => undefined)),
    );
  });
}

for (const { width, height } of [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 390, height: 844 },
  { width: 360, height: 800 },
]) {
  for (const theme of ["light", "dark"]) {
    test(`foundations at ${width}px in ${theme}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height });
      await openFixture(page, theme);
      const measurements = await page.evaluate(() => {
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 1;
        const ctx = canvas.getContext("2d")!;
        const luminance = (color: string) => {
          ctx.clearRect(0, 0, 1, 1);
          ctx.fillStyle = color;
          ctx.fillRect(0, 0, 1, 1);
          const rgb = Array.from(ctx.getImageData(0, 0, 1, 1).data)
            .slice(0, 3)
            .map((value) => value / 255)
            .map((value) =>
              value <= 0.04045
                ? value / 12.92
                : ((value + 0.055) / 1.055) ** 2.4,
            );
          return rgb[0]! * 0.2126 + rgb[1]! * 0.7152 + rgb[2]! * 0.0722;
        };
        const ratio = (a: string, b: string) => {
          const x = luminance(a),
            y = luminance(b);
          return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
        };
        const textPairs = Array.from(
          document.querySelectorAll(
            'span[role="status"], .xingxi-evidence, #foundation-form button:not(:disabled)',
          ),
        ).map((element) => {
          const style = getComputedStyle(element);
          return {
            label: element.textContent,
            contrast: ratio(style.color, style.backgroundColor),
          };
        });
        const input = getComputedStyle(document.querySelector("input")!);
        const panel = getComputedStyle(document.querySelector("section")!);
        return {
          textPairs,
          inputBorderContrast: ratio(
            input.borderTopColor,
            input.backgroundColor,
          ),
          panelRadius: panel.borderRadius,
          panelShadow: panel.boxShadow,
          buttonRadius: getComputedStyle(document.querySelector("button")!)
            .borderRadius,
          documentWidth: document.documentElement.scrollWidth,
          viewportWidth: innerWidth,
        };
      });
      await testInfo.attach("contrast-and-layout", {
        body: JSON.stringify(measurements, null, 2),
        contentType: "application/json",
      });
      for (const pair of measurements.textPairs)
        expect(pair.contrast, pair.label ?? "text").toBeGreaterThanOrEqual(4.5);
      expect(measurements.inputBorderContrast).toBeGreaterThanOrEqual(3);
      expect(measurements.panelRadius).toBe("10px");
      expect(measurements.buttonRadius).toBe("6px");
      expect(measurements.panelShadow).not.toBe("none");
      expect(measurements.documentWidth).toBeLessThanOrEqual(width);
      await page.screenshot({
        path: resolve(reportDir, `foundations-${width}-${theme}.png`),
        fullPage: true,
        animations: "disabled",
      });
    });
  }
}

test("native keyboard, validation and busy controls remain operable", async ({
  page,
}) => {
  await openFixture(page, "light");
  await page.evaluate(() =>
    document.querySelector("form")!.addEventListener("submit", (event) => {
      event.preventDefault();
      document.querySelector("output")!.textContent = new FormData(
        event.target as HTMLFormElement,
      ).get("topic") as string;
    }),
  );
  await page.getByRole("button", { name: "次要操作" }).click();
  await expect(page.locator("output")).toBeEmpty();
  await expect(page.getByRole("button", { name: "正在保存" })).toBeDisabled();
  await page.getByLabel("研究题目").fill("木渎方志研究");
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("研究问题")).toBeFocused();
  const outline = await page
    .getByLabel("研究问题")
    .evaluate((node) => getComputedStyle(node).outlineWidth);
  expect(outline).toBe("2px");
  await page.getByLabel("研究题目").press("Enter");
  await expect(page.locator("output")).toHaveText("木渎方志研究");
});

test("reduced motion stops continuous skeleton and spinner animation", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openFixture(page, "dark");
  const durations = await page
    .locator(".xingxi-skeleton, .animate-spin")
    .evaluateAll((nodes) =>
      nodes.map((node) => parseFloat(getComputedStyle(node).animationDuration)),
    );
  expect(durations.length).toBeGreaterThan(0);
  for (const duration of durations) expect(duration).toBeLessThanOrEqual(0.001);
});

test.describe("touch targets", () => {
  test.use({
    isMobile: true,
    hasTouch: true,
    viewport: { width: 390, height: 844 },
  });
  test("buttons, fields and evidence reach 44 CSS pixels", async ({ page }) => {
    await openFixture(page, "light");
    const heights = await page
      .locator(
        "#foundation-form button, #foundation-form input, .xingxi-evidence",
      )
      .evaluateAll((nodes) =>
        nodes.map((node) => node.getBoundingClientRect().height),
      );
    for (const height of heights) expect(height).toBeGreaterThanOrEqual(44);
  });
});

test("a shared header preserves readable action text in a legacy light surface", async ({
  page,
}) => {
  await openFixture(page, "dark");
  const colors = await page
    .getByRole("button", { name: "旧版操作" })
    .evaluate((node) => ({
      text: getComputedStyle(node).color,
      background: getComputedStyle(node).backgroundColor,
    }));
  expect(colors.text).toBe("rgb(32, 40, 43)");
  expect(colors.background).toBe("rgb(255, 255, 255)");
});

test("the migrated error retry still loads the real map page", async ({
  page,
}) => {
  mockLangGraphAPI(page);
  let unavailable = true;
  await page.route("**/api/map/catalog", (route) =>
    unavailable
      ? route.fulfill({ status: 503, json: { detail: "测试：暂时不可用" } })
      : route.fulfill({
          json: {
            updated_at: "2026-10-15",
            data_notice: "测试空目录",
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
  await page.goto("/workspace/map");
  const errorPanel = page.getByRole("alert").filter({
    has: page.getByRole("heading", { name: "地图资料暂时无法加载" }),
  });
  await expect(errorPanel).toBeVisible();
  unavailable = false;
  await page.getByRole("button", { name: "重新加载" }).click();
  await expect(errorPanel).toHaveCount(0);
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
});
