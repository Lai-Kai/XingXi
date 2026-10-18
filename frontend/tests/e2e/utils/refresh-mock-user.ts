import { expect, type Page } from "@playwright/test";

// SSR auth-disabled starts as the local administrator. Browser route mocks
// change the client user only after AuthProvider has installed its listener.
export async function refreshMockUser(page: Page) {
  let refreshed = false;
  const response = (item: { url: () => string; ok: () => boolean }) => {
    if (item.url().endsWith("/api/v1/auth/me") && item.ok()) refreshed = true;
  };
  page.on("response", response);
  try {
    await expect
      .poll(
        async () => {
          await page.evaluate(() =>
            document.dispatchEvent(new Event("visibilitychange")),
          );
          return refreshed;
        },
        { timeout: 10000, intervals: [100, 200, 500] },
      )
      .toBe(true);
  } finally {
    page.off("response", response);
  }
}
