import type { Locale } from "@/core/i18n/locale";

export function channelName(
  id: string,
  original: string,
  locale: Locale,
): string {
  const names: Record<string, string> = {
    feishu: "飞书",
    dingtalk: "钉钉",
    wechat: "微信",
    wecom: "企业微信",
  };
  return locale === "zh-CN" ? (names[id] ?? original) : original;
}

export function channelFieldLabel(
  name: string,
  _original: string,
  locale: Locale,
): string {
  const labels: Record<string, [string, string]> = {
    bot_token: ["机器人连接凭据", "Bot connection credential"],
    bot_username: ["机器人账号", "Bot account"],
    app_token: ["应用连接凭据", "App connection credential"],
    app_id: ["应用账号", "App account"],
    app_secret: ["应用连接密钥", "App connection key"],
    client_id: ["连接账号", "Connection account"],
    client_secret: ["连接密钥", "Connection key"],
    bot_id: ["机器人账号", "Bot account"],
    bot_secret: ["机器人连接密钥", "Bot connection key"],
  };
  const label = labels[name];
  return (
    label?.[locale === "zh-CN" ? 0 : 1] ??
    (locale === "zh-CN" ? "补充连接信息" : "Additional connection detail")
  );
}

export function channelUnavailableMessage(
  reason: string,
  locale: Locale,
): string {
  if (/not running/i.test(reason))
    return locale === "zh-CN"
      ? "消息连接尚未就绪，请稍后重试或联系管理员。"
      : "The message connection is not ready. Try again later or contact an administrator.";
  return locale === "zh-CN"
    ? "消息连接暂时不可用，请稍后重试或联系管理员。"
    : "The message connection is unavailable. Try again later or contact an administrator.";
}
