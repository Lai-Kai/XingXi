import { expect, test, type Page } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

declare global {
  interface Window {
    __xingxiNotifications?: Array<{ title: string; body?: string }>;
  }
}

async function installNotificationMock(
  page: Page,
  initialPermission: NotificationPermission = "default",
) {
  await page.addInitScript((permission) => {
    window.__xingxiNotifications = [];

    class MockNotification {
      static permission: NotificationPermission = permission;

      static async requestPermission(): Promise<NotificationPermission> {
        MockNotification.permission = "granted";
        return "granted";
      }

      onclick: (() => void) | null = null;
      onerror: ((error: Event) => void) | null = null;
      closed = false;

      constructor(title: string, options?: NotificationOptions) {
        window.__xingxiNotifications?.push({
          title,
          body: options?.body,
        });
      }

      close() {
        this.closed = true;
      }
    }

    Object.defineProperty(window, "Notification", {
      configurable: true,
      value: MockNotification,
    });
  }, initialPermission);
}

async function openNotificationSettings(page: Page) {
  await page.goto("/workspace/chats/new");
  const sidebar = page.locator("[data-sidebar='sidebar']");
  await sidebar.getByRole("button", { name: "设置", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "设置", exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "通知", exact: true }).click();
  return dialog;
}

test.describe("Notification settings", () => {
  test("can request permission and send the first test notification immediately", async ({
    page,
  }) => {
    mockLangGraphAPI(page);
    await installNotificationMock(page);

    const dialog = await openNotificationSettings(page);
    await dialog.getByRole("button", { name: "请求通知权限" }).click();

    await expect(dialog.getByRole("switch", { name: "通知" })).toBeChecked();

    await dialog.getByRole("button", { name: "发送测试通知" }).click();

    await expect
      .poll(() => page.evaluate(() => window.__xingxiNotifications ?? []))
      .toEqual([
        {
          title: "星羲",
          body: "这是一条测试通知。",
        },
      ]);
  });

  test("sends a completion notification when chat finishes while the page is unfocused", async ({
    page,
  }) => {
    mockLangGraphAPI(page);
    await installNotificationMock(page, "granted");
    await page.addInitScript(() => {
      Document.prototype.hasFocus = () => false;
    });

    await page.goto("/workspace/chats/new");

    const textarea = page.getByPlaceholder(
      "询问木渎古迹、人物、方志出处或历史沿革",
    );
    await expect(textarea).toBeVisible({ timeout: 15_000 });
    await textarea.fill("Run a one minute task");
    await textarea.press("Enter");

    await expect
      .poll(() => page.evaluate(() => window.__xingxiNotifications ?? []))
      .toEqual([
        {
          title: "New Chat",
          body: "Hello from DeerFlow!",
        },
      ]);
  });
});
