import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test.describe("Sidebar navigation", () => {
  test("sidebar contains research history and the Xingxi assistant", async ({
    page,
  }) => {
    mockLangGraphAPI(page);

    await page.goto("/workspace/chats/new");

    // Sidebar uses data-sidebar="menu-button" with asChild rendering on <Link>
    const sidebar = page.locator("[data-sidebar='sidebar']");
    await expect(sidebar.locator("a[href='/workspace/chats']")).toBeVisible({
      timeout: 15_000,
    });
    await expect(sidebar.locator("a[href='/workspace/agent']")).toBeVisible();
    await expect(sidebar.locator("a[href='/workspace/agents']")).toHaveCount(0);
  });

  test("assistant link navigates to the single Xingxi assistant", async ({
    page,
  }) => {
    mockLangGraphAPI(page);

    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-sidebar='sidebar']");
    const agentsLink = sidebar.locator("a[href='/workspace/agent']");
    await expect(agentsLink).toBeVisible({ timeout: 15_000 });
    await agentsLink.click();

    await page.waitForURL("**/workspace/agent");
    await expect(page).toHaveURL(/\/workspace\/agent$/);
  });

  test("Xingxi stays reachable when the generic agents API is off", async ({
    page,
  }) => {
    mockLangGraphAPI(page);
    await page.route("**/api/features", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ agents_api: { enabled: false } }),
      }),
    );

    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-sidebar='sidebar']");
    // Chats remains a real link; Agents is no longer a navigable link.
    await expect(sidebar.locator("a[href='/workspace/chats']")).toBeVisible({
      timeout: 15_000,
    });
    await expect(sidebar.locator("a[href='/workspace/agents']")).toHaveCount(0);

    const assistantLink = sidebar.getByRole("link", { name: "星羲研究助手" });
    await expect(assistantLink).toBeVisible();
    await assistantLink.focus();
    await expect(assistantLink).toBeFocused();
  });

  test("desktop sidebar can be reopened after collapsing", async ({ page }) => {
    mockLangGraphAPI(page);
    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-slot='sidebar']").first();
    const sidebarTrigger = sidebar.locator("[data-sidebar='trigger']");

    await expect(sidebarTrigger).toBeVisible({ timeout: 15_000 });
    await expect(sidebar).toHaveAttribute("data-state", "expanded");

    await sidebarTrigger.click();
    await expect(sidebar).toHaveAttribute("data-state", "collapsed");
    await expect(sidebar.locator("[data-sidebar='trigger']")).toBeVisible();

    await sidebar.locator("[data-sidebar='trigger']").click();
    await expect(sidebar).toHaveAttribute("data-state", "expanded");
  });

  test("desktop sidebar can be resized, collapsed, and dragged open repeatedly", async ({
    page,
  }) => {
    mockLangGraphAPI(page);
    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-slot='sidebar'][data-state]");
    const rail = sidebar.locator("[data-sidebar='rail']");
    await expect(rail).toBeVisible({ timeout: 15_000 });

    const dragRailTo = async (targetX: number) => {
      const railBox = await rail.boundingBox();
      expect(railBox).not.toBeNull();
      const y = railBox!.y + Math.min(80, railBox!.height / 2);

      await page.mouse.move(railBox!.x + railBox!.width / 2, y);
      await page.mouse.down();
      await expect(rail).toHaveAttribute("data-resizing", "true");
      await page.mouse.move(targetX, y, { steps: 4 });
      await page.mouse.up();

      await expect(rail).not.toHaveAttribute("data-resizing", "true");
      await expect
        .poll(() =>
          page.evaluate(() => ({
            cursor: document.body.style.cursor,
            userSelect: document.body.style.userSelect,
          })),
        )
        .toEqual({ cursor: "", userSelect: "" });
    };

    for (let cycle = 0; cycle < 2; cycle += 1) {
      await dragRailTo(80);
      await expect(sidebar).toHaveAttribute("data-state", "collapsed");

      await expect
        .poll(async () => {
          const box = await rail.boundingBox();
          return box ? Math.abs(box.x + box.width / 2 - 64) : Infinity;
        })
        .toBeLessThanOrEqual(1);

      await dragRailTo(280);
      await expect(sidebar).toHaveAttribute("data-state", "expanded");
      await expect
        .poll(async () => (await sidebar.boundingBox())?.width ?? 0)
        .toBeGreaterThanOrEqual(224);
      expect((await sidebar.boundingBox())!.width).toBeLessThanOrEqual(480);
    }

    const railLineColor = await rail.evaluate(
      (element) => getComputedStyle(element, "::after").backgroundColor,
    );
    expect(railLineColor).toBe("rgba(0, 0, 0, 0)");
  });

  test("desktop sidebar resize cleans up after outside release, Escape, and blur", async ({
    page,
  }) => {
    mockLangGraphAPI(page);
    await page.goto("/workspace/chats/new");

    const sidebar = page.locator("[data-slot='sidebar'][data-state]");
    const rail = sidebar.locator("[data-sidebar='rail']");
    await expect(rail).toBeVisible({ timeout: 15_000 });

    const pointerDownOnRail = async () => {
      const railBox = await rail.boundingBox();
      expect(railBox).not.toBeNull();
      const point = {
        x: railBox!.x + railBox!.width / 2,
        y: railBox!.y + Math.min(80, railBox!.height / 2),
      };
      await page.mouse.move(point.x, point.y);
      await page.mouse.down();
      await expect(rail).toHaveAttribute("data-resizing", "true");
      return point;
    };

    let point = await pointerDownOnRail();
    await page.mouse.move(700, point.y, { steps: 3 });
    await page.mouse.up();
    await expect(sidebar).toHaveAttribute("data-state", "expanded");
    await expect(rail).not.toHaveAttribute("data-resizing", "true");

    const maxWidthBox = await sidebar.boundingBox();
    expect(maxWidthBox).not.toBeNull();
    expect(maxWidthBox!.width).toBeCloseTo(480, 0);

    point = await pointerDownOnRail();
    await page.mouse.move(360, point.y, { steps: 2 });
    await page.keyboard.press("Escape");
    await page.mouse.up();
    await expect
      .poll(async () => Math.round((await sidebar.boundingBox())?.width ?? 0))
      .toBe(480);

    point = await pointerDownOnRail();
    await page.mouse.move(80, point.y, { steps: 2 });
    await page.evaluate(() => window.dispatchEvent(new Event("blur")));
    await page.mouse.up();
    await expect(sidebar).toHaveAttribute("data-state", "collapsed");
    await expect(rail).not.toHaveAttribute("data-resizing", "true");
    await expect
      .poll(() =>
        page.evaluate(() => ({
          cursor: document.body.style.cursor,
          userSelect: document.body.style.userSelect,
        })),
      )
      .toEqual({ cursor: "", userSelect: "" });
  });

  test("mobile welcome layout stays within viewport and opens sidebar", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    mockLangGraphAPI(page);

    await page.goto("/workspace/chats/new");

    const viewportWidth = page.viewportSize()?.width ?? 390;
    const expectInsideViewport = async (
      locator: ReturnType<typeof page.locator>,
    ) => {
      await expect(locator).toBeVisible({ timeout: 15_000 });
      const box = await locator.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(-1);
      expect(box!.x + box!.width).toBeLessThanOrEqual(viewportWidth + 1);
    };

    await expectInsideViewport(page.getByText(/^(Xingxi|星羲弦沚)$/).first());
    await expectInsideViewport(page.getByRole("textbox").first());
    await expectInsideViewport(page.locator("[data-slot='suggestions-list']"));

    const mobileSidebarTrigger = page
      .locator("[data-sidebar='trigger']:visible")
      .first();
    await expect(mobileSidebarTrigger).toBeVisible();
    await mobileSidebarTrigger.click();

    const mobileSidebar = page.locator(
      "[data-mobile='true'][data-sidebar='sidebar']",
    );
    await expect(mobileSidebar).toBeVisible();
    await expect(
      mobileSidebar.locator("a[href='/workspace/chats']"),
    ).toBeVisible();
    await expect(
      mobileSidebar.locator("a[href='/workspace/agent']"),
    ).toBeVisible();
  });
});
