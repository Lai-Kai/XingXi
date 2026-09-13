import { expect, test } from "@rstest/core";

import {
  dailyTopicContextForEntry,
  legacyModeRedirectHref,
  parseXingxiChatScope,
  xingxiChatHref,
} from "@/core/threads/xingxi-entry";

test("chat entry uses one canonical page without a mode parameter", () => {
  const href = xingxiChatHref("核验木渎商号");
  const url = new URL(href, "http://localhost");

  expect(url.pathname).toBe("/workspace/chats/new");
  expect(url.searchParams.has("mode")).toBe(false);
  expect(url.searchParams.get("prompt")).toBe("核验木渎商号");
  expect(url.searchParams.has("agent_name")).toBe(false);
  expect(xingxiChatHref("   ")).toBe("/workspace/chats/new");
});

test.each(["pro", "flash", "ultra"])(
  "legacy %s entry removes only the obsolete mode parameter",
  (mode) => {
    expect(
      legacyModeRedirectHref({
        mode,
        prompt: "核验木渎商号",
        document_id: ["document-1", "document-2"],
      }),
    ).toBe(
      "/workspace/chats/new?prompt=%E6%A0%B8%E9%AA%8C%E6%9C%A8%E6%B8%8E%E5%95%86%E5%8F%B7&document_id=document-1&document_id=document-2",
    );
  },
);

test("skill entry remains available to the shared chat page", () => {
  expect(legacyModeRedirectHref({ mode: "skill" })).toBeNull();
});

test("a daily topic carries its evidence and document scope into chat", () => {
  const href = xingxiChatHref("介绍灵岩山", {
    documentIds: ["document-1", "document-1", "document-2"],
    evidenceIds: ["evidence-1"],
    releaseId: "release-1",
    retrievalQuery: "灵岩山",
  });
  const url = new URL(href, "http://localhost");

  expect(url.searchParams.has("mode")).toBe(false);
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
