import { expect, test } from "@rstest/core";

import {
  channelFieldLabel,
  channelName,
  channelUnavailableMessage,
} from "@/core/channels/presentation";
import { zhCN } from "@/core/i18n/locales/zh-CN";

test("channel configuration displays Chinese labels while retaining provider and field IDs", () => {
  expect(channelName("feishu", "Feishu", "zh-CN")).toBe("飞书");
  expect(channelFieldLabel("bot_token", "Bot token", "zh-CN")).toBe(
    "机器人连接凭据",
  );
  expect(channelFieldLabel("custom", "机构配置", "zh-CN")).toBe("补充连接信息");
  expect(channelName("feishu", "Feishu", "en-US")).toBe("Feishu");
});

test("channel instructions preserve binding commands and the actual code without legacy branding", () => {
  expect(zhCN.channels.bindingInstruction("飞书", "code-123")).toContain(
    "/connect code-123",
  );
  expect(zhCN.channels.bindingInstruction("飞书", "code-123")).toContain(
    "星羲",
  );
  expect(
    channelUnavailableMessage(
      "Feishu channel is configured but is not running.",
      "zh-CN",
    ),
  ).toContain("尚未就绪");
  for (const locale of ["zh-CN", "en-US"] as const) {
    const message = channelUnavailableMessage(
      "数据库 API failure /srv/secret + debug=1",
      locale,
    );
    expect(message).not.toMatch(/数据库|API|srv|secret|debug/);
  }
});
