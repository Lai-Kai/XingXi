import { expect, test } from "@rstest/core";

import {
  modeContextForEntry,
  parseEntryMode,
  xingxiChatHref,
  XINGXI_ENTRY_MODES,
} from "@/core/threads/xingxi-entry";

test("deep exploration selects the real ultra model mode", () => {
  const href = xingxiChatHref("核验木渎商号", "ultra");
  const url = new URL(href, "http://localhost");

  expect(url.pathname).toBe("/workspace/chats/new");
  expect(url.searchParams.get("mode")).toBe("ultra");
  expect(url.searchParams.get("prompt")).toBe("核验木渎商号");
  expect(url.searchParams.has("research_mode")).toBe(false);
  expect(url.searchParams.has("agent_name")).toBe(false);
});

test("agent identity is not exposed as a selectable research mode", () => {
  expect(XINGXI_ENTRY_MODES.map((item) => item.id)).toEqual([
    "flash",
    "pro",
    "ultra",
  ]);
  expect(
    XINGXI_ENTRY_MODES.some((item) => item.id === ("agent" as never)),
  ).toBe(false);
});

test("entry mode is validated and mapped to runtime reasoning effort", () => {
  expect(parseEntryMode("ultra")).toBe("ultra");
  expect(parseEntryMode("agent")).toBeUndefined();
  expect(modeContextForEntry("ultra")).toEqual({
    mode: "ultra",
    thinking_enabled: true,
    reasoning_effort: "medium",
  });
  expect(modeContextForEntry("flash")).toEqual({
    mode: "flash",
    thinking_enabled: false,
    reasoning_effort: "minimal",
  });
});
