import { expect, test } from "@rstest/core";

import { settingsErrorMessage } from "@/core/settings/errors";

test("settings errors retain a known password correction and hide service failures", () => {
  expect(
    settingsErrorMessage(new Error("当前密码不正确"), "修改失败", "zh-CN"),
  ).toBe("当前密码不正确");
  expect(
    settingsErrorMessage(
      new Error("Authentication failed"),
      "修改失败",
      "zh-CN",
    ),
  ).toBe("修改失败");
  expect(settingsErrorMessage(null, "操作失败", "zh-CN")).toBe("操作失败");
});

test("service details stay hidden in both languages", () => {
  expect(
    settingsErrorMessage(
      new Error("Authentication failed"),
      "Try again",
      "en-US",
    ),
  ).toBe("Try again");
  expect(
    settingsErrorMessage(
      new Error("数据库 API 失败 /srv/private"),
      "请重试",
      "zh-CN",
    ),
  ).toBe("请重试");
});
