import { afterEach, expect, rs, test } from "@rstest/core";

import { getLocaleFromCookie, setLocaleInCookie } from "@/core/i18n/cookies";
import { detectLocale, normalizeLocale } from "@/core/i18n/locale";
import { formatTimeAgo } from "@/core/utils/datetime";

afterEach(() => {
  rs.unstubAllGlobals();
  rs.doUnmock("next/headers");
  rs.resetModules();
});

test("an English browser starts in Chinese until a Xingxi preference is selected", () => {
  rs.stubGlobal("window", {});
  rs.stubGlobal("navigator", { language: "en-US" });
  expect(detectLocale()).toBe("zh-CN");
  expect(normalizeLocale(undefined)).toBe("zh-CN");
});

test("legacy English cookies do not override the Xingxi default", () => {
  rs.stubGlobal("document", { cookie: "locale=en-US; other=value" });
  expect(getLocaleFromCookie()).toBeNull();
  expect(formatTimeAgo(Date.now() - 60_000)).toMatch(/前/);
});

test("explicit Xingxi language choices persist independently of legacy cookies", () => {
  const documentMock = { cookie: "locale=zh-CN; xingxi_locale=en-US" };
  rs.stubGlobal("document", documentMock);
  expect(getLocaleFromCookie()).toBe("en-US");
  expect(formatTimeAgo(Date.now() - 60_000)).toMatch(/ago/);
  setLocaleInCookie("zh-CN");
  expect(documentMock.cookie).toContain("xingxi_locale=zh-CN;");
});

test("malformed cookies fall back safely to Chinese", () => {
  rs.stubGlobal("document", { cookie: "xingxi_locale=%not-encoded" });
  expect(normalizeLocale(getLocaleFromCookie())).toBe("zh-CN");
});

test("server rendering ignores legacy English and respects explicit Xingxi language choices", async () => {
  const cookieValues: Record<string, string> = { locale: "en-US" };
  const writes = rs.fn();
  rs.doMock("next/headers", () => ({
    cookies: async () => ({
      get: (name: string) => {
        const value = cookieValues[name];
        return value ? { value } : undefined;
      },
      set: writes,
    }),
  }));
  const { detectLocaleServer, setLocale } = await import("@/core/i18n/server");
  expect(await detectLocaleServer()).toBe("zh-CN");
  cookieValues.xingxi_locale = "en-US";
  expect(await detectLocaleServer()).toBe("en-US");
  await setLocale("zh-CN");
  expect(writes.mock.calls[0]?.slice(0, 2)).toEqual(["xingxi_locale", "zh-CN"]);
});
