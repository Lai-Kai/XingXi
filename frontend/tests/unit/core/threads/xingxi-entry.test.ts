import { expect, test } from "@rstest/core";

import {
  dailyTopicContextForEntry,
  modeContextForEntry,
  parseXingxiChatScope,
  parseEntryMode,
  xingxiChatHref,
  xingxiWorkspaceHref,
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

test("mode entry opens the existing workspace before creating a chat", () => {
  expect(xingxiWorkspaceHref("pro")).toBe("/workspace?mode=pro");
  expect(xingxiWorkspaceHref("flash")).toBe("/workspace?mode=flash");
  expect(xingxiChatHref("   ", "flash")).toBe(
    "/workspace/chats/new?mode=flash",
  );
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

test("a daily topic carries its evidence and document scope into chat", () => {
  const href = xingxiChatHref("介绍灵岩山", "pro", {
    documentIds: ["document-1", "document-1", "document-2"],
    evidenceIds: ["evidence-1"],
    releaseId: "release-1",
    retrievalQuery: "灵岩山",
  });
  const url = new URL(href, "http://localhost");

  expect(url.searchParams.getAll("document_id")).toEqual([
    "document-1",
    "document-2",
  ]);
  expect(url.searchParams.getAll("evidence_id")).toEqual(["evidence-1"]);
  expect(url.searchParams.get("release_id")).toBe("release-1");
  expect(url.searchParams.get("topic_query")).toBe("灵岩山");
  expect(
    dailyTopicContextForEntry(parseXingxiChatScope(url.searchParams)),
  ).toEqual({
    daily_topic_query: "灵岩山",
    daily_topic_document_ids: ["document-1", "document-2"],
    daily_topic_evidence_ids: ["evidence-1"],
    daily_topic_release_id: "release-1",
  });
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
