import type { Locale } from "@/core/i18n/locale";
import { publicErrorMessage } from "@/core/ui/presentation";

export function settingsErrorMessage(
  error: unknown,
  fallback: string,
  locale: Locale,
): string {
  const message = error instanceof Error ? error.message : error;
  // Preserve a useful password correction without reflecting arbitrary service text.
  if (
    message === "当前密码不正确" ||
    message === "Current password is incorrect"
  ) {
    return locale === "zh-CN"
      ? "当前密码不正确"
      : "Current password is incorrect";
  }
  return publicErrorMessage(error, fallback);
}
