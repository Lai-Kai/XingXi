export type XingxiEntryMode = "flash" | "pro" | "ultra";

export const XINGXI_ENTRY_MODES: ReadonlyArray<{
  id: XingxiEntryMode;
  label: string;
}> = [
  { id: "flash", label: "快速问答" },
  { id: "pro", label: "专业研究" },
  { id: "ultra", label: "深度求索" },
];

export function parseEntryMode(
  value: string | null,
): XingxiEntryMode | undefined {
  return value === "flash" || value === "pro" || value === "ultra"
    ? value
    : undefined;
}

export function modeContextForEntry(mode: XingxiEntryMode) {
  return {
    mode,
    thinking_enabled: mode !== "flash",
    reasoning_effort:
      mode === "ultra"
        ? ("medium" as const)
        : mode === "pro"
          ? ("medium" as const)
          : ("minimal" as const),
  };
}

export function xingxiChatHref(prompt: string, mode: XingxiEntryMode) {
  const params = new URLSearchParams({ mode, prompt });
  return `/workspace/chats/new?${params.toString()}`;
}
