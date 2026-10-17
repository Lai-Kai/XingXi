import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

const evidenceDir = process.env.UI_SHELL_DIR;
const desktopSidebar = "[data-slot='sidebar'][data-state]";
const mobileSidebar = "[data-mobile='true'][data-sidebar='sidebar']";

async function mockShell(page: Page) {
  await page.route("**/api/**", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "工作区测试：服务暂不可用" },
    }),
  );
  mockLangGraphAPI(page, {
    threads: [
      {
        thread_id: "00000000-0000-0000-0000-000000000001",
        title: "木渎水系与古镇变迁考据",
        updated_at: "2026-10-15T01:00:00Z",
      },
    ],
  });
}

async function capture(page: Page, name: string) {
  if (!evidenceDir) return;
  await mkdir(evidenceDir, { recursive: true });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({
    path: resolve(evidenceDir, `${name}.png`),
    animations: "disabled",
  });
  const metadata = await page.evaluate(() => ({
    route: location.pathname + location.search,
    viewport: { width: innerWidth, height: innerHeight },
    documentWidth: document.documentElement.scrollWidth,
    theme: document.documentElement.className,
    sidebar: document
      .querySelector("[data-slot='sidebar'][data-state]")
      ?.getAttribute("data-state"),
    scenario: "mock-empty-or-unavailable",
  }));
  await writeFile(
    resolve(evidenceDir, `${name}.json`),
    JSON.stringify(metadata, null, 2),
  );
}

async function expectWidth(page: Page, width: number) {
  await expect
    .poll(async () =>
      Math.round(
        (await page.locator("[data-slot='sidebar-container']").boundingBox())
          ?.width ?? 0,
      ),
    )
    .toBe(width);
}

test.beforeEach(async ({ page }) => {
  await mockShell(page);
});

for (const theme of ["light", "dark"]) {
  test(`desktop groups, brand, collapse and cookie persistence (${theme})`, async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.addInitScript(
      (value) => localStorage.setItem("theme", value),
      theme,
    );
    await page.goto("/workspace/glossary");
    const sidebar = page.locator(desktopSidebar);
    await expect(sidebar).toHaveAttribute("data-state", "expanded");
    await expectWidth(page, 260);
    const nav = sidebar.getByRole("navigation", { name: "工作区导航" });
    for (const group of ["核心研究", "时空人文", "文献与治理"]) {
      await expect(nav.getByText(group, { exact: true })).toBeVisible();
    }
    await expect(nav.getByRole("link")).toHaveCount(13);
    await expect(nav.locator("a[aria-current='page']")).toHaveAttribute(
      "href",
      "/workspace/glossary",
    );
    await expect(nav.locator("a[href='/workspace/agents']")).toHaveCount(0);
    await expect(sidebar.locator("img")).toBeVisible();
    await expect
      .poll(() =>
        sidebar
          .locator("img")
          .evaluate((node) => (node as HTMLImageElement).naturalWidth),
      )
      .toBeGreaterThan(0);
    await capture(page, `desktop-expanded-${theme}`);
    await sidebar
      .getByRole("button", { name: "收起侧栏", exact: true })
      .click();
    await expectWidth(page, 64);
    await nav.getByRole("link", { name: "文献库", exact: true }).hover();
    await expect(page.getByRole("tooltip")).toContainText("文献库");
    await capture(page, `desktop-collapsed-${theme}`);
    await page.reload();
    await expect(sidebar).toHaveAttribute("data-state", "collapsed");
    await expectWidth(page, 64);
    expect(
      (await context.cookies()).find(
        (cookie) => cookie.name === "sidebar_state",
      )?.value,
    ).toBe("false");
    await page.keyboard.press("Control+b");
    await expectWidth(page, 260);
    await page.reload();
    await expectWidth(page, 260);
  });
}

test("tablet defaults follow viewport until the user chooses a state", async ({
  page,
  context,
}) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.goto("/workspace/glossary");
  await expectWidth(page, 64);
  await capture(page, "tablet-default-light");
  expect(
    (await context.cookies()).find((cookie) => cookie.name === "sidebar_state"),
  ).toBeUndefined();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expectWidth(page, 260);
  await page.setViewportSize({ width: 1024, height: 768 });
  await expectWidth(page, 64);
  await page
    .locator(desktopSidebar)
    .getByRole("button", { name: "展开侧栏", exact: true })
    .click();
  await expectWidth(page, 260);
  await page.reload();
  await expectWidth(page, 260);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expectWidth(page, 260);
});

for (const state of ["true", "false"]) {
  test(`tablet respects explicit sidebar Cookie ${state}`, async ({
    page,
    context,
    baseURL,
  }) => {
    await context.addCookies([
      { name: "sidebar_state", value: state, url: baseURL! },
    ]);
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/workspace/glossary");
    await expectWidth(page, state === "true" ? 260 : 64);
    await page.reload();
    await expectWidth(page, state === "true" ? 260 : 64);
  });
}

for (const width of [390, 360]) {
  for (const theme of ["light", "dark"]) {
    test(`mobile drawer, focus, history and navigation ${width} ${theme}`, async ({
      page,
      context,
      baseURL,
    }) => {
      await context.addCookies([
        { name: "sidebar_state", value: "false", url: baseURL! },
      ]);
      await page.setViewportSize({ width, height: width === 390 ? 844 : 800 });
      await page.addInitScript(
        (value) => localStorage.setItem("theme", value),
        theme,
      );
      await page.goto("/workspace/glossary");
      const header = page.locator("[data-workspace-mobile-header]");
      await expect(header).toBeVisible();
      expect((await header.boundingBox())!.height).toBe(48);
      const trigger = header.getByRole("button", {
        name: "展开侧栏",
        exact: true,
      });
      const triggerBox = (await trigger.boundingBox())!;
      expect(triggerBox.width).toBeGreaterThanOrEqual(44);
      expect(triggerBox.height).toBeGreaterThanOrEqual(44);
      await capture(page, `mobile-page-${width}-${theme}`);
      await trigger.click();
      const drawer = page.locator(mobileSidebar);
      await expect(drawer).toBeVisible();
      await expect(drawer.getByRole("navigation")).toBeVisible();
      await drawer
        .getByRole("link", { name: "异名辨析", exact: true })
        .scrollIntoViewIfNeeded();
      await expect(
        drawer.getByRole("link", { name: "异名辨析", exact: true }),
      ).toBeVisible();
      await drawer
        .getByRole("link", { name: "木渎水系与古镇变迁考据", exact: true })
        .scrollIntoViewIfNeeded();
      await expect(
        drawer.getByRole("link", {
          name: "木渎水系与古镇变迁考据",
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        drawer.getByRole("button", { name: "账户设置", exact: true }),
      ).toBeVisible();
      await capture(page, `mobile-drawer-${width}-${theme}`);
      await page.keyboard.press("Tab");
      expect(
        await drawer.evaluate((node) => node.contains(document.activeElement)),
      ).toBe(true);
      await page.keyboard.press("Shift+Tab");
      expect(
        await drawer.evaluate((node) => node.contains(document.activeElement)),
      ).toBe(true);
      await page.keyboard.press("Escape");
      await expect(drawer).toBeHidden();
      await expect(trigger).toBeFocused();
      await trigger.click();
      await drawer.getByRole("link", { name: "古文展签", exact: true }).click();
      await expect(drawer).toBeHidden();
      await header.getByRole("link", { name: "文史检索", exact: true }).click();
      await expect(page).toHaveURL(/\/workspace$/);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(width);
    });
  }
}

test("mobile account settings closes back into the drawer", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workspace/glossary");
  await page
    .locator("[data-workspace-mobile-header]")
    .getByRole("button", { name: "展开侧栏", exact: true })
    .click();
  const drawer = page.locator(mobileSidebar);
  await drawer.getByRole("button", { name: "账户设置", exact: true }).click();
  const settings = page.getByRole("dialog").last();
  await expect(
    settings.getByText("default@test.local", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeVisible();
  await expect(
    drawer.getByRole("button", { name: "账户设置", exact: true }),
  ).toBeFocused();
});

test("skip link and command palette remain keyboard accessible", async ({
  page,
}) => {
  await page.goto("/workspace/glossary");
  const skip = page.getByRole("link", { name: "跳转到工作区内容" });
  await skip.focus();
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#workspace-content")).toBeFocused();
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("mobile long workspace forms scroll with the page header fixed", async ({
  page,
}) => {
  await page.setViewportSize({ width: 360, height: 640 });
  await page.goto("/workspace/scheduled-tasks");
  const createButton = page
    .getByTestId("scheduled-task-create-form")
    .getByRole("button", { name: "Create", exact: true });
  await expect(createButton).toBeAttached();
  expect((await createButton.boundingBox())!.y).toBeGreaterThan(640);
  await page.mouse.move(220, 400);
  await page.mouse.wheel(0, 1200);
  await expect
    .poll(async () => {
      const box = await createButton.boundingBox();
      return !!box && box.y >= 48 && box.y + box.height <= 640;
    })
    .toBe(true);
  expect(
    (await page
      .locator("#workspace-content > .workspace-page-container > header")
      .boundingBox())!.y,
  ).toBe(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    360,
  );
});
